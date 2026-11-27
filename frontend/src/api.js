/* Переходник между экранами и API агента (контракт в корневом README, раздел «API для фронтенда»).
   Экраны чата и кабинета говорят на своём простом языке (/chat/..., /cases...). Этот файл переводит
   их запросы в вызовы сервера и ответы сервера обратно в форму, которую рисуют экраны.

   Ключей здесь нет:
   - X-Demo-Key подставляет веб-сервер перед API и только для POST /sessions (Caddy на стенде, scripts/serve.mjs локально),
     дальше чат ходит с токеном разговора;
   - ключ менеджера кабинет спрашивает один раз полем и держит до закрытия вкладки.
   Историю разговора хранит сервер: чат восстанавливает её после перезагрузки и опрашивает новые реплики по after.
   Чего в API пока нет, отвечает 404: экран сообщает, что данные недоступны. */
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
  function two(n) { return (n < 10 ? '0' : '') + n; }
  function clock(iso) { var d = new Date(iso); return isNaN(d) ? '' : d.getHours() + ':' + two(d.getMinutes()); }
  function money(rubles) { return String(Math.round(rubles)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ₽'; }
  // две буквы названия без формы собственности: ООО «Северная линия» → СЛ. Посетителя сайта сервер не знает по имени
  function initials(who) {
    var s = String(who || '').replace(/^(ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО)\s+/i, '').replace(/[«»"']/g, '').trim();
    if (!s || who === 'Посетитель сайта') return 'К';
    return s.split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join('').toUpperCase();
  }
  // короткое имя позиции для строки очереди: до первой цифры, скобки или тире
  function shortName(name) {
    var s = String(name || 'позиция каталога').split(/\s[\d(–—-]|,/)[0].trim();
    return s.length > 36 ? s.slice(0, 35).replace(/\s+\S*$/, '') + '…' : s;
  }

  // почему агент позвал менеджера: заголовок карточки и одна фраза о причине
  var REASON = {
    discount_over_limit: { title: 'Клиент просит скидку больше 5%', why: 'Агент может дать только купон 5%, клиент просит больше.' },
    customer_request: { title: 'Клиент просит менеджера', why: 'Клиент попросил живого человека или пишет о тендере.' },
    server_license: { title: 'Лицензия на сервер', why: 'Цену серверной лицензии агент не называет.' },
    price_confirmation: { title: 'Уточнить цену', why: 'В каталоге нет цены или позиция недоступна.' },
    catalog_unavailable: { title: 'Позиции нет в каталоге', why: 'Агент не нашёл позицию, клиенту нужна замена.' }
  };
  var ANSWER_EFFECT = 'Ответ уйдёт клиенту в этот же чат **от имени менеджера**, обращение закроется.';
  // срок ответа: агент обещает клиенту ответ менеджера через 2 минуты после последней реплики
  var ANSWER_MIN = 2;

  function requisites(q) { return [q.inn ? 'ИНН ' + q.inn : '', q.kpp ? 'КПП ' + q.kpp : ''].filter(Boolean).join(', '); }
  function sourceDate(s) { var d = s && new Date(s); return d && !isNaN(d) ? two(d.getDate()) + '.' + two(d.getMonth() + 1) + '.' + d.getFullYear() : ''; }

  // случай сервера {id, version, state, reason, quote, created, updated, first_client_message} → карточка кабинета
  function toCase(v) {
    var q = v.quote, why = REASON[v.reason] || { title: 'Запрос клиента', why: 'Агент передал разговор менеджеру.' };
    var who = q && q.customer ? q.customer : 'Посетитель сайта';
    var at = utc(v.updated || v.created);
    var c = {
      id: v.id, version: v.version, reason: v.reason, status: v.state === 'pending' ? 'waiting' : 'done',
      client: who, initials: initials(who), first: v.first_client_message || '',
      summary: v.summary || '', reason_text: v.reason_text || '',
      deadline: at && !isNaN(Date.parse(at)) ? new Date(Date.parse(at) + ANSWER_MIN * 60000).toISOString() : null,
      steps: null, talk: null, talk_earlier: [], help_option: false, can_discount: false
    };
    if (q) {
      var offer = q.offer || {}, qty = q.quantity || 1, price = offer.price_kopecks != null ? offer.price_kopecks / 100 : (q.amount_kopecks || 0) / 100 / qty;
      c.kind = 'quote'; c.deadline_label = 'Отправить до';
      c.queue_title = q.items && q.items.length > 1 ? 'КП на ' + q.items.length + ' позиции' : 'КП на ' + shortName(offer.name);
      c.title = who + ': ' + c.queue_title;
      c.amount_rub = rub(q.amount_kopecks || 0);
      c.facts = [['Клиент', who], ['Сумма', money(c.amount_rub)]];
      c.kp = {
        buyer: [who, requisites(q)].filter(Boolean).join(', '), vat_rate: 0,
        discount: q.discount_percent || 0,
        items: q.items && q.items.length ? q.items.map(function (item) {
          return { name: item.name, qty: item.quantity, price: rub(item.price_kopecks),
            note: item.requested && item.requested !== item.quantity ? 'Клиент просил ' + item.requested + ', в КП ' + item.quantity + ' по фасовке каталога' : '' };
        }) : [{ name: offer.name || 'Позиция каталога', qty: qty, price: price, note: q.requested_users && q.requested_users !== qty ? 'Клиент просил ' + q.requested_users + ', в КП ' + qty + ' по фасовке каталога' : '' }],
        terms: [['Оплата', q.payment_terms || 'Предоплата'], ['НДС', q.vat_status || 'Уточняет менеджер']].concat(q.source_date ? [['Цена каталога на', sourceDate(q.source_date)]] : [])
      };
      c.effect = 'После отправки клиент получит в этот же чат **КП файлом PDF**.';
    } else {
      c.kind = 'answer'; c.deadline_label = 'Ответ до';
      c.queue_title = c.title = why.title;
      c.facts = [['Клиент', who]];
      c.reply_draft = '';
      c.help_option = true;
      c.effect = why.why + '\n' + ANSWER_EFFECT;
    }
    return c;
  }
  // решённый случай остаётся в журнале закрытой карточкой
  function closeCase(c, v) {
    c.version = v.version; c.status = 'done'; c.done_tone = v.state === 'rejected' ? 'neutral' : 'success';
    var note = String(v.decision_note || '').trim(), at = v.updated ? ' в ' + clock(utc(v.updated)) : '';
    if (v.state === 'approved') {
      c.done_label = (c.kind === 'quote' ? 'КП отправлено' : 'Ответ отправлен') + at;
      c.effect = c.kind === 'quote' ? 'Клиент получил в чат **КП файлом PDF**.' : 'Менеджер ответил клиенту' + (note ? ': «' + note + '»' : '.');
    } else if (v.state === 'rejected') {
      c.done_label = 'Отказано' + at;
      c.effect = 'Менеджер отказал' + (note ? ': «' + note + '»' : '.');
    } else {
      c.done_label = 'Отвечал агент';
      c.effect = 'Агент отвечал клиенту сам, менеджер не понадобился.';
    }
    return c;
  }

  var known = {}, attempts = {};
  function casesList() {
    return manager('GET', '/manager/cases').then(function (r) {
      // тот же случай отдаём тем же объектом: кабинет дописывает в него переписку и шаги
      var list = (r.cases || []).map(function (v) {
        var was = known[v.id];
        if (was && was.version === v.version) return was;
        return (known[v.id] = toCase(v));
      });
      // решённые здесь остаются в журнале до перезагрузки, сервер в очереди отдаёт только ожидающие
      Object.keys(known).forEach(function (id) { if (known[id].status !== 'waiting' && !list.some(function (c) { return c.id === id; })) list.push(known[id]); });
      return { cases: list, recent: [] };
    });
  }

  // кабинет шлёт {action: approve | answer, reply_text}. Сервер знает два ответа: approve с необязательным текстом и reject
  function decide(id, body) {
    var c = known[id]; if (!c) return Promise.reject(fail(404));
    if (body.discount_percent) return Promise.reject(fail(404)); // правки скидки в API пока нет
    var choice = body.action === 'refuse' ? 'reject' : 'approve';
    var reply = String(body.reply_text || '').trim().slice(0, 400);
    // повтор после обрыва связи идёт с тем же request_id, сервер не решит дважды
    var remember = !!body.add_to_help;
    var key = id + ':' + c.version + ':' + choice + ':' + reply + ':' + remember;
    var rid = attempts[key] || (attempts[key] = uuid());
    var data = { choice: choice, version: c.version, request_id: rid, remember: remember };
    if (reply) data.reply = reply;
    return manager('POST', '/manager/cases/' + encodeURIComponent(id) + '/decision', data).then(function (v) {
      v.updated = nowIso(); closeCase(c, v); c.knowledge = v.knowledge; return c;
    });
  }

  // шаги агента из журнала обращения: время и что сделано, одной строкой на событие
  var TOOL = { clarify_requirements: 'уточнил требования', search_catalog: 'искал в каталоге', check_registry: 'проверил реестр', draft_quote: 'собрал черновик КП', contact_manager: 'передал менеджеру' };
  function stepText(e) {
    var d = e.detail || '';
    switch (e.event) {
      case 'opened': return 'клиент открыл чат';
      case 'catalog_search': return 'искал в каталоге';
      case 'registry_lookup': return 'проверил реестр';
      case 'quote_amount_calculated': return 'посчитал сумму ' + money(+d / 100);
      case 'price_calculated': return 'посчитал цену';
      case 'sent_to_manager': return d === 'quote_review' ? 'передал КП менеджеру на проверку' : 'передал менеджеру' + (REASON[d] ? ': ' + REASON[d].title.charAt(0).toLowerCase() + REASON[d].title.slice(1) : '');
      case 'demo_coupon_offered': return 'предложил купон ' + d + '%';
      case 'model_unavailable': return 'модель не ответила, ответил по правилам';
      case 'model_budget_exceeded': return 'лимит модели потрачен, ответил по правилам';
      case 'manager_decision': return d === 'rejected' ? 'менеджер отказал' : 'менеджер ответил';
      case 'catalog_quote_sent': return 'КП ушло клиенту в чат';
      case 'knowledge_saved': return 'ответ менеджера сохранён в «Знаниях»';
      case 'knowledge_answer': return 'ответил из базы знаний';
      case 'model_tool_executed': return TOOL[d] || '';
    }
    return '';
  }
  function toSteps(events) {
    var out = [];
    (events || []).forEach(function (e) {
      var text = stepText(e), at = clock(utc(e.created));
      if (!text || (out.length && out[out.length - 1][1] === text)) return;
      out.push([at, text]);
    });
    return out;
  }
  function toTalk(messages) {
    return (messages || []).map(function (m) {
      var who = m.role === 'client' ? 'client' : m.role === 'manager' ? 'manager' : 'agent';
      return { who: who, name: who === 'manager' ? 'Менеджер' : undefined, text: (m.text || '') + (m.document_url ? ' Файл: ' + FILE_NAME : '') };
    });
  }
  function events(id) {
    var path = '/manager/cases/' + encodeURIComponent(id);
    return manager('GET', path + '/journal').then(function (r) {
      var cost = 0; (r.usage || []).forEach(function (u) { cost += +u.cost_microrubles || 0; });
      var res = { steps: toSteps(r.events), talk: toTalk(r.messages) };
      if ((r.usage || []).length) res.cost = [['Работа агента', (cost / 1e6).toFixed(2).replace('.', ',') + ' ₽'], ['Вызовов модели', String(r.usage.length)]];
      return res;
    }, function (e) {
      if (e.status !== 404) throw e;
      // сервер без журнала обращения: только переписка
      return manager('GET', path + '/messages').then(function (r) { return { steps: [], talk: toTalk(r.messages) }; });
    });
  }

  // Журнал: все разговоры стенда. Ждущие решения ведут в «Сегодня», остальные открываются закрытой карточкой
  var jKnown = {};
  function toJournal(v) {
    var c = toCase(v), q = v.quote;
    var it = { id: v.id, time: utc(v.updated || v.created), client: c.client, inn: q ? [q.inn, q.kpp].filter(Boolean).join(' ') : '' };
    var first = String(v.first_client_message || '').replace(/\s+/g, ' ').trim();
    if (first.length > 64) first = first.slice(0, 63).replace(/\s+\S*$/, '') + '…';
    // разговор без КП и без передачи отличается от соседних первой фразой клиента
    // клиент стоит в строке отдельно, заголовок его не повторяет
    it.title = q || REASON[v.reason] ? c.queue_title : first ? '«' + first + '»' : 'Разговор с агентом';
    if (v.state === 'pending') { it.case_id = v.id; it.status = { tone: 'neutral', text: 'Ждёт ответа', open: true }; return it; }
    closeCase(c, v);
    if (!q && !REASON[v.reason]) c.title = it.title;
    it.detail = c;
    it.status = { tone: c.done_tone, text: c.done_label.replace(/ в \d{1,2}:\d{2}$/, '') };
    return it;
  }
  function journalList() {
    return manager('GET', '/manager/cases?state=all&limit=100&offset=0').then(function (r) {
      return { items: (r.cases || []).map(function (v) {
        var was = jKnown[v.id], sig = v.state + ':' + v.version + ':' + (v.updated || '');
        if (was && was._sig === sig) return was;
        var it = toJournal(v); it._sig = sig; jKnown[v.id] = it; return it;
      }) };
    });
  }

  // ключ менеджера: одно окно поверх кабинета, ключ живёт до закрытия вкладки
  var asked = false;
  function askKey(status) {
    if (asked || !document.getElementById('view')) return; asked = true;
    var scrim = document.createElement('div');
    scrim.className = 'scrim';
    var box = document.createElement('form');
    box.className = 'dialog';
    box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-labelledby', 'keyTitle');
    box.innerHTML = '<h2 class="h2" id="keyTitle">Вход в кабинет менеджера</h2>' +
      '<p class="dialog__text">' + (status === 503 ? 'На сервере агента не задан ключ менеджера. Попросите администратора стенда.' : 'Введите ключ менеджера стенда. Он хранится только в этой вкладке.') + '</p>' +
      (status === 503 ? '' : '<input class="field" type="password" autocomplete="off" required minlength="24" placeholder="Ключ менеджера" aria-label="Ключ менеджера">' +
      '<div class="dialog__buttons"><button class="btn btn--accent" type="submit">Войти</button></div>');
    box.addEventListener('submit', function (e) {
      e.preventDefault(); write(MANAGER_KEY, box.querySelector('input').value.trim()); location.reload();
    });
    scrim.appendChild(box);
    document.body.appendChild(scrim);
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
    if (method === 'GET' && path === '/knowledge') return manager('GET', '/manager/knowledge');
    // правка скидки, чат менеджера с клиентом, возврат агенту, пауза и лимит, справка, статистика, настройки
    // и проверка разговоров из журнала: в API их пока нет, экран покажет пример и пометит это строкой сверху
    return Promise.reject(fail(404));
  }

  function downloadCases() {
    return fetch(API + '/manager/cases/export.csv', { credentials: 'same-origin', headers: managerHeaders() })
      .then(function (r) { if (!r.ok) throw fail(r.status); return r.blob(); })
      .then(function (blob) {
        var url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = 'cases.csv'; a.click();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      });
  }

  window.SupportBackend = { call: call, downloadCases: downloadCases };
})();
