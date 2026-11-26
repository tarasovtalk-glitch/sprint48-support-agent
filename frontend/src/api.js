/* Переходник между экранами и API агента (контракт в корневом README, раздел «API для фронтенда»).
   Экраны чата и кабинета говорят на своём простом языке (/chat/..., /cases...). Этот файл переводит
   их запросы в вызовы сервера и ответы сервера обратно в форму, которую рисуют экраны.

   Ключей здесь нет:
   - X-Demo-Key подставляет веб-сервер перед API (nginx на стенде, scripts/serve.mjs локально);
   - ключ менеджера кабинет спрашивает один раз полем и держит до закрытия вкладки.
   Чего в API пока нет, отвечает 404: экран тогда показывает пример и пишет об этом строкой сверху. */
(function () {
  'use strict';
  var CFG = window.SUPPORT_CONFIG || {};
  var API = String(CFG.apiBase || '/support/api').replace(/\/$/, '');
  var MANAGER_KEY = 'sl-manager-key';
  var LOG = 'sl-support-log:';

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
  function rubText(kopecks) { return rub(kopecks).toLocaleString('ru-RU', { minimumFractionDigits: 2 }).replace(/\s/g, ' ') + ' ₽'; }
  function dmy(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? m[3] + '.' + m[2] + '.' + m[1] : iso || ''; }
  // время журнала из SQLite приходит как «ГГГГ-ММ-ДД ЧЧ:ММ:СС» в UTC
  function utc(s) { return s && !/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s.replace(' ', 'T') + 'Z' : s; }
  function total(o) { return o.renewal_total_kopecks != null ? o.renewal_total_kopecks : (o.renewal_unit_kopecks || 0) * (o.quantity || 0); }

  /* ---------- Чат ---------- */
  var ACTIONS = { price: 'price', quote: 'quote', invoice: 'invoice', deferral: 'deferral' };
  var CHOICE = [
    { id: 'price', text: 'Узнать цену' }, { id: 'quote', text: 'Получить КП' },
    { id: 'invoice', text: 'Выставить счёт' }, { id: 'deferral', text: 'Нужна отсрочка' }
  ];
  var GREETING = 'Здравствуйте! Я ИИ-помощник магазина, отвечаю сразу по каталогу, заказам и счетам. Что не решу сам, передам менеджеру вместе с перепиской.';
  var FILES = { quote: 'Коммерческое предложение.pdf', invoice: 'Черновик счёта.pdf' };

  // У сервера нет истории сообщений, поэтому переписку держим во вкладке: после перезагрузки она та же
  function chatLog(sid) { try { return JSON.parse(read(LOG + sid) || 'null'); } catch (e) { return null; } }
  function saveLog(sid, log) { write(LOG + sid, JSON.stringify(log)); }
  function push(log, m) { m.seq = ++log.seq; m.time = m.time || nowIso(); log.messages.push(m); return m; }
  function bearer(sid) { return { Authorization: 'Bearer ' + sid }; }

  // что сказать клиенту, когда менеджер решил: текст из состояния обращения и заметки менеджера
  function decisionMessage(view) {
    var note = view.decision_note ? ' ' + view.decision_note : '';
    if (view.state === 'approved') return 'Менеджер согласовал отсрочку. Оплатить до ' + dmy(view.payment_due) + '.' + note;
    if (view.state === 'rejected') return 'Менеджер отказал в отсрочке.' + note;
    return '';
  }

  function chatOpen() {
    return raw('POST', '/sessions').then(function (r) {
      var sid = r.session_token, log = { seq: 0, messages: [], state: r.case && r.case.state, version: r.case && r.case.version };
      push(log, { from: 'agent', type: 'text', text: GREETING });
      saveLog(sid, log);
      return { session_id: sid, messages: log.messages.slice() };
    });
  }

  function chatSend(sid, data) {
    var log = chatLog(sid); if (!log) return Promise.reject(fail(404));
    var action = data.button_id && ACTIONS[data.button_id];
    var body = action ? { action: action, channel: 'chat' } : { text: data.text, channel: 'chat' };
    push(log, { from: 'client', type: 'text', text: data.text });
    var start = log.seq;
    return raw('POST', '/case/messages', body, bearer(sid)).then(function (r) {
      var m = { from: 'agent', type: r.document_url ? 'file' : 'text', text: r.reply };
      if (r.document_url) m.file = { name: FILES[r.intent] || 'Документ.pdf', url: r.document_url };
      // сервер не понял фразу: даём те же варианты кнопками-ответами, без скидок
      if (r.intent === 'unknown') m.buttons = CHOICE;
      push(log, m);
      if (r.case) { log.state = r.case.state; log.version = r.case.version; }
      saveLog(sid, log);
      return { messages: log.messages.slice(start) };
    }, function (e) { saveLog(sid, log); throw e; });
  }

  // раз в 3 секунды: не решил ли менеджер. Новое сообщение появляется только при смене состояния
  function chatPoll(sid, after) {
    var log = chatLog(sid); if (!log) return Promise.reject(fail(404));
    var since = function () { return { messages: log.messages.filter(function (m) { return m.seq > after; }) }; };
    // восстановление после перезагрузки: кнопки-ответы живы только у последнего сообщения
    if (after === 0) {
      var last = log.messages.length - 1;
      return Promise.resolve({ messages: log.messages.map(function (m, i) {
        if (i === last || !m.buttons) return m;
        var c = {}; for (var k in m) if (k !== 'buttons') c[k] = m[k]; return c;
      }) });
    }
    return raw('GET', '/case', null, bearer(sid)).then(function (view) {
      if (view.version !== log.version) {
        var was = log.state; log.state = view.state; log.version = view.version;
        if (was === 'pending' && view.state !== 'pending') {
          var text = decisionMessage(view);
          if (text) push(log, { from: 'agent', type: 'text', text: text });
        }
        saveLog(sid, log);
      }
      return since();
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

  var STATUS = { pending: 'waiting', approved: 'approved', rejected: 'refused', open: 'waiting' };
  var REFUSE = 'Отсрочка не положена по условиям магазина';
  function toCase(v) {
    var o = v.offer || {}, days = o.requested_days;
    var c = {
      id: v.id, version: v.version, kind: 'approve', status: STATUS[v.state] || 'waiting',
      title: (o.customer || 'Клиент') + ': отсрочка ' + days + ' дней',
      amount_rub: rub(total(o)),
      desc: [o.product, o.quantity ? o.quantity + ' узлов' : '', o.previous_order ? 'прошлый заказ № ' + o.previous_order : ''].filter(Boolean).join(' · '),
      approve_label: 'Согласовать ' + days + ' дней',
      effect: 'Агент сразу напишет клиенту в чат, до какого числа оплатить',
      refuse_reasons: [REFUSE],
      refuse_reply: 'Отсрочку согласовать не можем: по условиям магазина счёт оплачивается до отгрузки.',
      decided_at: null, decided_by: null, result: null
    };
    if (v.state === 'approved') c.result = 'Согласовано. Агент написал клиенту: оплатить до ' + dmy(v.payment_due);
    if (v.state === 'rejected') c.result = 'Отказано. Агент передал клиенту ответ' + (v.decision_note ? ': ' + v.decision_note : '');
    if (v.state !== 'pending') c.decided_at = nowIso();
    return c;
  }

  var known = {}, attempts = {};
  function casesList() {
    return manager('GET', '/manager/cases').then(function (r) {
      var list = (r.cases || []).map(toCase);
      list.forEach(function (c) { known[c.id] = c; });
      // решённые здесь за сессию остаются на экране, сервер отдаёт только ожидающие
      Object.keys(known).forEach(function (id) {
        if (known[id].status !== 'waiting' && !list.some(function (c) { return c.id === id; })) list.push(known[id]);
      });
      // статистики дня в API нет: блок «Агент сегодня закрыл сам…» не показываем
      return { cases: list, review: [], today: null };
    });
  }

  function decide(id, body) {
    var c = known[id]; if (!c) return Promise.reject(fail(404));
    var choice = body.action === 'approve' ? 'approve' : 'reject';
    var note = choice === 'reject' ? String(body.reply_text || body.reason || '').slice(0, 500) : '';
    // повтор после обрыва связи идёт с тем же request_id, сервер не решит дважды
    var key = id + ':' + c.version + ':' + choice + ':' + note;
    var rid = attempts[key] || (attempts[key] = uuid());
    return manager('POST', '/manager/cases/' + encodeURIComponent(id) + '/decision',
      { choice: choice, version: c.version, request_id: rid, note: note }).then(function (v) {
      var next = toCase(v); known[id] = next; return next;
    }, function (e) {
      if (e.status === 409) toastText('Обращение уже изменилось. Обновите страницу');
      throw e;
    });
  }

  var EVENT = {
    received: 'Клиент написал в чат', price_calculated: 'Агент посчитал цену', document_prepared: 'Агент подготовил документ',
    rule_applied: 'Агент применил правило договора', sent_to_manager: 'Агент передал запрос менеджеру',
    manager_decision: 'Менеджер принял решение', contract_rule_saved: 'Менеджер сохранил правило договора',
    model_unavailable: 'Модель не ответила, агент спросил клиента кнопками', channel_result: 'Ответ клиенту'
  };
  function events(id) {
    return manager('GET', '/manager/cases/' + encodeURIComponent(id) + '/journal').then(function (r) {
      return { events: (r.events || []).map(function (e) {
        return { actor: e.event === 'manager_decision' || e.event === 'contract_rule_saved' ? 'manager' : e.event === 'received' ? 'client' : 'agent',
          text: EVENT[e.event] || e.event, time: utc(e.created) };
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
