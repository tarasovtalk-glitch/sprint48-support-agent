/* Переходник между экранами и API агента (контракт в корневом README, раздел «API для фронтенда»).
   Экраны чата и кабинета говорят на своём простом языке (/chat/..., /cases...). Этот файл переводит
   их запросы в вызовы сервера и ответы сервера обратно в форму, которую рисуют экраны.

   Ключей здесь нет:
   - X-Demo-Key подставляет веб-сервер перед API и только для POST /sessions (Caddy на стенде, scripts/serve.mjs локально),
     дальше чат ходит с токеном разговора;
   - ключ менеджера кабинет спрашивает один раз полем и держит до закрытия вкладки.
   Историю разговора хранит сервер: чат восстанавливает её после перезагрузки и опрашивает новые реплики по after.
   Чего в API пока нет, отвечает 404: экран тогда показывает пример и пишет об этом строкой сверху. */
(function () {
  'use strict';
  var CFG = window.SUPPORT_CONFIG || {};
  var API = String(CFG.apiBase || '/support/api').replace(/\/$/, '');
  var MANAGER_KEY = 'sl-manager-key';

  function fail(status, text) { var e = new Error(text || 'HTTP ' + status); e.status = status; return e; }
  function raw(method, path, body, headers) {
    var h = headers || {};
    if (body) h['Content-Type'] = 'application/json';
    return fetch(API + path, { method: method, credentials: 'same-origin', headers: h, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) {
        if (!r.ok) {
          var error = fail(r.status);
          if (r.status === 429) error.retryAfter = Number(r.headers.get('Retry-After'));
          throw error;
        }
        return r.status === 204 ? {} : r.json();
      });
  }
  function read(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function write(k, v) { try { if (v == null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch (e) {} }
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16);
    });
  }
  function nowIso() { return new Date().toISOString(); }
  function rub(kopecks) { return Math.round(kopecks) / 100; }
  // время журнала из SQLite приходит как «ГГГГ-ММ-ДД ЧЧ:ММ:СС» в UTC
  function utc(s) { return s && !/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s.replace(' ', 'T') + 'Z' : s; }

  /* ---------- Чат ---------- */
  // запасные кнопки, если сервер не прислал своих и не понял фразу (старый режим сервера без истории)
  var CHOICE = [
    { label: 'Узнать цену', action: 'price', value: '' }, { label: 'Получить КП', action: 'quote', value: '' },
    { label: 'Выставить счёт', action: 'invoice', value: '' }, { label: 'Нужна отсрочка', action: 'deferral', value: '' }
  ];
  var GREETING = 'Здравствуйте! Я ИИ-помощник магазина, отвечаю сразу по каталогу, заказам и счетам. Что не решу сам, передам менеджеру вместе с перепиской.';
  var FILE_NAME = 'Коммерческое предложение.pdf';
  var pressable = {}, pressSeq = 0; // id кнопки на экране → {action, value} для сервера
  function bearer(sid) { return { Authorization: 'Bearer ' + sid }; }
  // карточка товара, с которой клиент открыл чат: /support/?page=<адрес карточки>. Сервер берёт из неё позицию,
  // когда клиент пишет о покупке. Принимаем только https://store.softline.ru/, не длиннее 600 знаков, как на сервере
  var STORE_PAGE = /^https:\/\/store\.softline\.ru\//i;
  var PAGE_URL = (function () {
    var p = ''; try { p = new URLSearchParams(location.search).get('page') || ''; } catch (e) {}
    if (!STORE_PAGE.test(p)) p = document.referrer || '';
    return STORE_PAGE.test(p) && p.length <= 600 ? p : '';
  })();

  // реплика сервера {id, role, text, document_url, buttons, created} → сообщение экрана
  function toMessage(r, keepButtons) {
    var m = { seq: r.id, from: r.role, type: r.document_url ? 'file' : 'text', text: r.text || '', time: utc(r.created) };
    if (r.document_url) m.file = { name: FILE_NAME, url: r.document_url };
    if (keepButtons && r.buttons && r.buttons.length) {
      m.buttons = r.buttons.filter(function (b) { return b && b.label && b.action; }).map(function (b, i) {
        var id = 'b' + (++pressSeq);
        pressable[id] = { action: b.action, value: b.value || '' };
        return { id: id, text: b.label };
      });
    }
    return m;
  }
  // кнопки-ответы живы только у последней реплики агента: старые после перезагрузки не возвращаем
  function toMessages(list) {
    var last = -1;
    list.forEach(function (r, i) { if (r.role !== 'client') last = i; });
    return list.map(function (r, i) { return toMessage(r, i === last); });
  }

  function chatOpen() {
    return raw('POST', '/sessions').then(function (r) {
      return { session_id: r.session_token, messages: [{ from: 'agent', type: 'text', text: GREETING }] };
    });
  }

  function chatSend(sid, data) {
    var b = data.button_id && pressable[data.button_id];
    var body = b ? { action: b.action, value: b.value } : { text: data.text };
    if (PAGE_URL) body.page_url = PAGE_URL;
    return raw('POST', '/case/messages', body, bearer(sid)).then(function (r) {
      if (Array.isArray(r.messages)) return { messages: toMessages(r.messages) };
      // сервер без истории сообщений: собираем ответ из reply
      var list = Array.isArray(r.buttons) && r.buttons.length ? r.buttons : r.intent === 'unknown' ? CHOICE : [];
      var m = toMessage({ role: 'agent', text: r.reply, document_url: r.document_url, buttons: list }, true);
      delete m.seq;
      return { messages: [m] };
    });
  }

  // history: вся беседа с приветствием после перезагрузки страницы. Опрос идёт по after и приветствие
  // не добавляет: до первой реплики клиента after = 0, иначе приветствие приходило бы с каждым опросом
  function chatPoll(sid, after, history) {
    var q = after ? '?after=' + after : '';
    return raw('GET', '/case/messages' + q, null, bearer(sid)).then(function (r) {
      var list = toMessages(r.messages || []);
      if (history) list.unshift({ from: 'agent', type: 'text', text: GREETING });
      return { messages: list };
    });
  }

  /* ---------- Кабинет ---------- */
  function managerHeaders() { return { 'X-Manager-Key': read(MANAGER_KEY) || '' }; }
  function manager(method, path, body) {
    return raw(method, path, body, managerHeaders()).catch(function (e) {
      if (e.status === 401 || e.status === 403 || e.status === 503) askKey(e.status);
      throw e;
    });
  }

  // почему агент позвал менеджера: заголовок карточки, сводка и что произойдёт после ответа
  var REASON = {
    quote_review: { title: 'Проверить КП' },
    discount_over_limit: { title: 'Клиент просит скидку больше 5%', advice: 'Агент предложил купон 5% по правилу магазина, клиент просит больше. Решите, что ответить: агент передаст ваш ответ в чат.' },
    customer_request: { title: 'Клиент просит оператора', advice: 'Клиент попросил живого человека или пишет о тендере. Переписка ниже, ответьте ему в тот же чат.' },
    server_license: { title: 'Лицензия на сервер', advice: 'Клиенту нужна серверная лицензия, агент не называл её цену. Напишите клиенту цену и условия.' },
    price_confirmation: { title: 'Уточнить цену', advice: 'В каталоге нет цены или позиция недоступна. Напишите клиенту цену и срок.' },
    catalog_unavailable: { title: 'Позиция недоступна в каталоге', advice: 'Агент не нашёл позицию в каталоге. Ответьте клиенту, что предложить вместо неё.' }
  };
  var STATUS = { pending: 'waiting', approved: 'approved', rejected: 'refused', open: 'waiting' };

  // реквизиты покупателя из КП: ИНН и КПП рядом, через запятую
  function requisites(q) { return [q.inn ? 'ИНН ' + q.inn : '', q.kpp ? 'КПП ' + q.kpp : ''].filter(Boolean).join(', '); }

  function toCase(v) {
    var q = v.quote, why = REASON[v.reason] || { title: 'Запрос клиента', advice: 'Агент передал разговор менеджеру. Переписка ниже.' };
    var who = q && q.customer ? q.customer : 'Посетитель сайта';
    var c = { id: v.id, version: v.version, status: STATUS[v.state] || 'waiting', reason: v.reason, decided_at: null, decided_by: null, result: null };
    if (q) {
      var offer = q.offer || {};
      c.kind = 'approve';
      c.title = who + ': КП, ' + (offer.name || 'позиция каталога');
      c.amount_rub = rub(q.amount_kopecks || 0);
      c.desc = [q.quantity ? q.quantity + ' шт.' : '', requisites(q), q.payment_terms || '', q.vat_status || ''].filter(Boolean).join(' · ');
      c.approve_label = 'Отправить КП в чат';
      c.effect = 'Клиент получит PDF коммерческого предложения в этом же чате';
      c.refuse_reasons = ['Позиция не подходит под задачу клиента'];
      c.refuse_reply = 'Проверили запрос: эта позиция вам не подойдёт. Подскажу другой вариант здесь же, в чате.';
    } else {
      c.kind = 'answer';
      c.title = why.title;
      c.desc = who;
      c.advice = why.advice;
      c.help_option = false;
      c.effect = 'Агент передаст ваш ответ клиенту в тот же чат';
    }
    return c;
  }
  function decidedCase(c, v) {
    var next = {}; for (var k in c) next[k] = c[k];
    next.version = v.version; next.status = STATUS[v.state] || c.status; next.decided_at = nowIso();
    if (c.kind === 'answer' && v.state !== 'pending') next.status = 'answered';
    if (next.status === 'approved') next.result = v.document_url ? 'КП отправлено клиенту в чат' : 'Ответ отправлен клиенту';
    if (next.status === 'refused') next.result = 'Отказано. Клиент получил ответ в чате' + (v.decision_note ? ': ' + v.decision_note : '');
    if (next.status === 'answered') next.result = 'Ответ отправлен клиенту: ' + (v.decision_note || '');
    return next;
  }

  var known = {}, attempts = {};
  function casesList() {
    return manager('GET', '/manager/cases').then(function (r) {
      // тот же случай отдаём тем же объектом: кабинет дописывает в него переписку, пока идёт обновление очереди
      var list = (r.cases || []).map(function (v) {
        var c = toCase(v), was = known[c.id];
        if (was && was.version === c.version && was.status === c.status) return was;
        known[c.id] = c; return c;
      });
      // решённые здесь за сессию остаются на экране, сервер отдаёт только ожидающие
      Object.keys(known).forEach(function (id) {
        if (known[id].status !== 'waiting' && !list.some(function (c) { return c.id === id; })) list.push(known[id]);
      });
      // статистики дня в API нет: блок «Агент сегодня закрыл сам…» не показываем
      return { cases: list, review: [], today: null };
    });
  }

  // approve: КП уходит клиенту (или ответ менеджера), reject: отказ с текстом. reply необязателен, до 400 знаков
  function decide(id, body) {
    var c = known[id]; if (!c) return Promise.reject(fail(404));
    var choice = body.action === 'refuse' ? 'reject' : 'approve';
    var reply = String(body.reply_text || '').trim().slice(0, 400);
    // повтор после обрыва связи идёт с тем же request_id, сервер не решит дважды
    var key = id + ':' + c.version + ':' + choice + ':' + reply;
    var rid = attempts[key] || (attempts[key] = uuid());
    var data = { choice: choice, version: c.version, request_id: rid };
    if (reply) data.reply = reply;
    return manager('POST', '/manager/cases/' + encodeURIComponent(id) + '/decision', data).then(function (v) {
      var next = decidedCase(c, v); known[id] = next; return next;
    }, function (e) {
      if (e.status === 409) toastText('Обращение уже изменилось. Обновите страницу');
      throw e;
    });
  }

  // «Как шёл разговор»: реплики клиента, агента и менеджера с временем. Имени клиента сервер не знает.
  // Журнал обращения (GET /manager/cases/{id}/journal) добавляет под репликой агента его шаги: какой инструмент
  // выбрала модель (model_tool_executed), что сделал сервер (поиск, реестр, расчёт, передача), и расход модели (usage)
  var ACTOR = { client: 'Клиент', manager: 'Менеджер' };
  var TOOL = { clarify_requirements: 'уточнение требований', search_catalog: 'поиск по каталогу', check_registry: 'проверка реестра',
    draft_quote: 'черновик КП', contact_manager: 'передача менеджеру' };
  function rubText(kopecks) { return (Math.round(+kopecks) / 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 }).replace(/\s/g, '\u00a0') + '\u00a0₽'; }
  function step(e) {
    var d = e.detail || '';
    switch (e.event) {
      case 'model_tool_executed': return { key: d, model: true, text: TOOL[d] || d };
      case 'catalog_search': return { key: 'search_catalog', text: 'поиск по каталогу' };
      case 'registry_lookup': return { key: 'check_registry', text: 'проверка реестра' };
      case 'quote_amount_calculated': return { key: 'calc', text: 'расчёт ' + rubText(d) };
      case 'price_calculated': return { key: 'calc', text: 'расчёт цены' };
      case 'sent_to_manager': return { key: 'contact_manager', text: d === 'quote_review' ? 'КП передано менеджеру на проверку'
        : 'передача менеджеру' + (REASON[d] ? ': ' + REASON[d].title.charAt(0).toLowerCase() + REASON[d].title.slice(1) : '') };
      case 'demo_coupon_offered': return { key: 'coupon', text: 'купон ' + d + '%' };
      case 'model_unavailable': return { key: 'down', text: 'модель не ответила, ответ по правилам' };
      case 'model_budget_exceeded': return { key: 'limit', text: 'лимит модели исчерпан, ответ по правилам' };
    }
    return null;
  }
  // шаги одной реплики: «Модель выбрала: черновик КП. Сделано: расчёт 70 300 ₽, передача менеджеру: проверить КП»
  function stepsLine(list) {
    var chosen = {}, model = [], done = [];
    list.forEach(function (s) { if (s.model && !chosen[s.key]) { chosen[s.key] = true; model.push(s.text); } });
    list.forEach(function (s) { if (!s.model && !chosen[s.key] && done.indexOf(s.text) < 0) done.push(s.text); });
    return (model.length ? 'Модель выбрала: ' + model.join(', ') + '.' : '') + (model.length && done.length ? ' ' : '') + (done.length ? 'Сделано: ' + done.join(', ') : '');
  }
  function toEvents(messages, journal) {
    var steps = (journal || []).map(function (e) { var s = step(e); if (s) s.at = e.created || ''; return s; }).filter(Boolean), k = 0;
    return (messages || []).map(function (m) {
      var ev = { actor: m.role, name: ACTOR[m.role], text: (m.text || '') + (m.document_url ? ' Файл: ' + FILE_NAME : ''), time: utc(m.created) };
      if (m.role !== 'client') {
        // шаги, записанные до этой реплики (время в журнале с точностью до секунды)
        var mine = []; while (k < steps.length && steps[k].at <= (m.created || '')) mine.push(steps[k++]);
        var line = stepsLine(mine); if (line) ev.steps = line;
      }
      return ev;
    });
  }
  function events(id) {
    var path = '/manager/cases/' + encodeURIComponent(id);
    return manager('GET', path + '/journal').then(function (r) {
      var usage = r.usage || [], cost = 0;
      usage.forEach(function (u) { cost += +u.cost_microrubles || 0; });
      return { events: toEvents(r.messages, r.events), model_calls: usage.length, model_cost_rub: cost / 1e6 };
    }, function (e) {
      if (e.status !== 404) throw e;
      // сервер без журнала обращения: только переписка
      return manager('GET', path + '/messages').then(function (r) { return { events: toEvents(r.messages) }; });
    });
  }

  // Журнал: все разговоры стенда, новые сверху. Время разговора в списке сервер пока не отдаёт
  var STATE_SIDE = { open: 'идёт разговор', pending: 'ждёт решения', rejected: 'отказано' };
  function toJournal(v) {
    var q = v.quote, why = REASON[v.reason], offer = (q && q.offer) || {};
    var who = q && q.customer ? q.customer : 'Посетитель сайта';
    var it = { id: v.id, channel: 'чат', client: who, review: false, open: v.state === 'open' || v.state === 'pending' };
    // название позиции из фида длинное: в строке и заголовке только клиент и количество, позиция строкой ниже заголовка
    // первое сообщение клиента отличает разговоры без КП и без причины передачи друг от друга
    var first = String(v.first_client_message || '').replace(/\s+/g, ' ').trim();
    if (first.length > 64) first = first.slice(0, 63).replace(/\s+\S*$/, '') + '…';
    it.title = q ? who + ': КП' + (q.quantity ? ' на ' + q.quantity + ' шт.' : '') : why ? why.title : first ? '«' + first + '»' : 'Разговор с агентом';
    // в карточке справа реплика видна в переписке, заголовок её не повторяет
    if (first) { it.first = first; if (!q && !why) it.detail_title = 'Разговор с агентом'; }
    if (q) { it.client = [offer.name || 'Позиция каталога', requisites(q)].filter(Boolean).join(' · '); it.inn = [q.inn, q.kpp].filter(Boolean).join(' '); }
    it.meta = (q ? 'Проверка КП' : why ? who : 'Агент отвечал сам') + ' · чат';
    if (q && q.amount_kopecks != null) it.value_rub = rub(q.amount_kopecks);
    it.status = v.state === 'approved' ? (q ? 'КП отправлено' : 'ответ отправлен') : STATE_SIDE[v.state] || '';
    it.badge = v.state === 'pending' ? { tone: 'warning', text: 'Ждёт вашего решения во вкладке «Сегодня»' }
      : v.state === 'approved' ? { tone: 'success', text: q ? 'КП отправлено клиенту в чат' : 'Ответ отправлен клиенту в чат' }
      : v.state === 'rejected' ? { tone: 'neutral', text: 'Отказано, клиент получил ответ в чате' }
      : { tone: 'neutral', text: 'Агент ведёт разговор сам' };
    if (v.decision_note) it.next = 'Ответ менеджера: ' + v.decision_note;
    if (v.created || v.updated) {
      // время последнего сообщения в строке журнала: сегодня часы, раньше ещё и дата
      it.time = utc(v.updated || v.created);
      var d = new Date(it.time), now = new Date(), two = function (n) { return (n < 10 ? '0' : '') + n; };
      if (!isNaN(d)) it.meta += ' · ' + (d.toDateString() === now.toDateString() ? '' : two(d.getDate()) + '.' + two(d.getMonth() + 1) + ' ') + two(d.getHours()) + ':' + two(d.getMinutes());
    }
    return it;
  }
  // кабинет перечитывает журнал при каждом выборе строки: тот же разговор отдаём тем же объектом,
  // чтобы загруженная переписка не пропадала и не запрашивалась по кругу
  var jKnown = {};
  function journalList() {
    return manager('GET', '/manager/cases?state=all&limit=50&offset=0').then(function (r) {
      return { items: (r.cases || []).map(function (v) {
        var was = jKnown[v.id], sig = v.state + ':' + v.version + ':' + (v.updated || '');
        if (was && was._sig === sig) return was;
        var it = toJournal(v); it._sig = sig; jKnown[v.id] = it; return it;
      }) };
    });
  }

  function toastText(text) { var el = document.getElementById('toast'); if (el) { el.textContent = text; el.classList.add('is-on'); setTimeout(function () { el.classList.remove('is-on'); }, 2600); } }

  // ключ менеджера: одно поле поверх кабинета, ключ живёт до закрытия вкладки
  var asked = false;
  function askKey(status) {
    if (asked || !document.getElementById('view')) return; asked = true;
    var box = document.createElement('form');
    box.className = 'panel key-form';
    box.setAttribute('aria-label', 'Вход в кабинет');
    box.innerHTML = '<div class="panel__head"><h2 class="t-h2">Вход в кабинет менеджера</h2></div>' +
      '<p class="panel__note">' + (status === 503 ? 'На сервере агента не задан ключ менеджера. Попросите администратора стенда.' : 'Введите ключ менеджера стенда. Он хранится только в этой вкладке.') + '</p>' +
      (status === 503 ? '' : '<label class="field" style="max-width:none"><input type="password" autocomplete="off" required minlength="24" placeholder="Ключ менеджера" aria-label="Ключ менеджера"></label>' +
      '<button class="btn btn--primary" type="submit">Войти</button>');
    box.addEventListener('submit', function (e) {
      e.preventDefault(); write(MANAGER_KEY, box.querySelector('input').value.trim()); location.reload();
    });
    document.body.appendChild(box);
    var input = box.querySelector('input'); if (input) input.focus();
  }

  /* ---------- маршруты экранов ---------- */
  function call(method, path, body) {
    var m;
    if (method === 'POST' && path === '/chat/sessions') return chatOpen();
    if ((m = /^\/chat\/sessions\/([^/]+)\/messages(?:\?after=(\d+))?$/.exec(path))) {
      var sid = decodeURIComponent(m[1]);
      // без after: восстановить разговор целиком, с after: только новые реплики
      return method === 'POST' ? chatSend(sid, body || {}) : chatPoll(sid, +(m[2] || 0), m[2] == null);
    }
    if (/^\/chat\/sessions\/[^/]+\/rating$/.test(path)) return Promise.resolve({}); // оценки в API пока нет
    if (method === 'GET' && path === '/access') return manager('GET', '/manager/access');
    if (method === 'GET' && path === '/agent/metrics') return manager('GET', '/manager/metrics');
    if (method === 'GET' && path === '/cases') return casesList();
    if ((m = /^\/cases\/([^/]+)\/decision$/.exec(path))) return decide(decodeURIComponent(m[1]), body || {});
    if ((m = /^\/cases\/([^/]+)\/events$/.exec(path))) return events(decodeURIComponent(m[1]));
    if (method === 'GET' && path === '/journal') return journalList();
    if (method === 'GET' && (m = /^\/journal\/([^/]+)$/.exec(path))) return events(decodeURIComponent(m[1]));
    // справка, статистика и настройки агента, проверка разговоров из журнала: в API их пока нет, экран покажет пример
    return Promise.reject(fail(404));
  }

  window.SupportBackend = { call: call };
})();
