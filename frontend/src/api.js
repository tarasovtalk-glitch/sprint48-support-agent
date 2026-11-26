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
        if (!r.ok) throw fail(r.status);
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
    return raw('POST', '/case/messages', body, bearer(sid)).then(function (r) {
      if (Array.isArray(r.messages)) return { messages: toMessages(r.messages) };
      // сервер без истории сообщений: собираем ответ из reply
      var list = Array.isArray(r.buttons) && r.buttons.length ? r.buttons : r.intent === 'unknown' ? CHOICE : [];
      var m = toMessage({ role: 'agent', text: r.reply, document_url: r.document_url, buttons: list }, true);
      delete m.seq;
      return { messages: [m] };
    });
  }

  // after = 0: вся беседа после перезагрузки страницы, иначе только новые реплики (ответ менеджера, PDF)
  function chatPoll(sid, after) {
    var q = after ? '?after=' + after : '';
    return raw('GET', '/case/messages' + q, null, bearer(sid)).then(function (r) {
      var list = toMessages(r.messages || []);
      if (!after) list.unshift({ from: 'agent', type: 'text', text: GREETING });
      return { messages: list };
    });
  }

  /* ---------- Кабинет ---------- */
  function managerHeaders() { return { 'X-Manager-Key': read(MANAGER_KEY) || '' }; }
  function manager(method, path, body) {
    return raw(method, path, body, managerHeaders()).catch(function (e) {
      if (e.status === 401 || e.status === 503) askKey(e.status);
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

  function toCase(v) {
    var q = v.quote, why = REASON[v.reason] || { title: 'Запрос клиента', advice: 'Агент передал разговор менеджеру. Переписка ниже.' };
    var who = q && q.customer ? q.customer : 'Посетитель сайта';
    var c = { id: v.id, version: v.version, status: STATUS[v.state] || 'waiting', reason: v.reason, decided_at: null, decided_by: null, result: null };
    if (q) {
      var offer = q.offer || {};
      c.kind = 'approve';
      c.title = who + ': КП, ' + (offer.name || 'позиция каталога');
      c.amount_rub = rub(q.amount_kopecks || 0);
      c.desc = [q.quantity ? q.quantity + ' шт.' : '', q.inn ? 'ИНН ' + q.inn : '', q.payment_terms || '', q.vat_status || ''].filter(Boolean).join(' · ');
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

  // «Как шёл разговор»: реплики клиента, агента и менеджера с временем
  function events(id) {
    return manager('GET', '/manager/cases/' + encodeURIComponent(id) + '/messages').then(function (r) {
      return { events: (r.messages || []).map(function (m) {
        return { actor: m.role, text: m.text + (m.document_url ? '\n' + FILE_NAME : ''), time: utc(m.created) };
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
      return method === 'POST' ? chatSend(sid, body || {}) : chatPoll(sid, +(m[2] || 0));
    }
    if (/^\/chat\/sessions\/[^/]+\/rating$/.test(path)) return Promise.resolve({}); // оценки в API пока нет
    if (method === 'GET' && path === '/cases') return casesList();
    if ((m = /^\/cases\/([^/]+)\/decision$/.exec(path))) return decide(decodeURIComponent(m[1]), body || {});
    if ((m = /^\/cases\/([^/]+)\/events$/.exec(path))) return events(decodeURIComponent(m[1]));
    // журнал, справка, статистика и настройки агента: в API их пока нет, экран покажет пример
    return Promise.reject(fail(404));
  }

  window.SupportBackend = { call: call };
})();
