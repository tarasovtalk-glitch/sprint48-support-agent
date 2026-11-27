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
    if (r.document_url) m.file = { name: /черновик сч[её]та/i.test(r.text || '') ? 'Черновик счёта.pdf' : FILE_NAME, url: r.document_url };
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

  // почему агент позвал менеджера: заголовок карточки и одна фраза о причине (все 19 причин из summary.py)
  var REASON = {
    quote_review: { title: 'Черновик КП на проверку', why: 'Агент собрал черновик КП по каталогу, нужна проверка перед отправкой.' },
    quote_multi: { title: 'Черновик КП на проверку', why: 'Агент собрал черновик КП на несколько позиций, нужна проверка.' },
    discount_over_limit: { title: 'Клиент просит скидку больше 5%', why: 'Агент может дать только купон 5%, клиент просит больше.' },
    customer_request: { title: 'Клиент просит менеджера', why: 'Клиент попросил подключить живого менеджера.' },
    server_license: { title: 'Лицензия на сервер', why: 'Цену серверной лицензии агент не называет.' },
    price_confirmation: { title: 'Сверить цену и количество', why: 'В каталоге нет подтверждённой цены или нужно сверить комплектацию.' },
    catalog_unavailable: { title: 'Каталог недоступен', why: 'Агент не смог проверить позицию в каталоге.' },
    not_in_catalog: { title: 'Товара нет в каталоге', why: 'Агент не нашёл позицию в каталоге, нужна проверка или замена.' },
    order_question: { title: 'Вопрос по заказу', why: 'У агента нет доступа к заказам, нужен менеджер.' },
    activation_problem: { title: 'Не активируется ключ', why: 'Клиент сообщил о проблеме с активацией ключа.' },
    tender: { title: 'Тендер или госзакупка', why: 'Условия для тендера или госзакупки готовит менеджер.' },
    request_status: { title: 'Статус заявки', why: 'Клиент уточняет статус ранее отправленного запроса.' },
    payment_question: { title: 'Вопрос оплаты', why: 'Нетиповой вопрос по условиям оплаты, нужен менеджер.' },
    needs_manager: { title: 'Нужен менеджер', why: 'Агент передал нестандартный запрос менеджеру.' },
    deferral: { title: 'Просит отсрочку', why: 'Отсрочку и постоплату агент не обещает, исключения решает менеджер.' },
    model_routing: { title: 'Не распознан запрос', why: 'Агент не уверен в ответе и передал разговор человеку.' },
    complaint: { title: 'Жалоба клиента', why: 'Клиент недоволен обслуживанием, требуется участие менеджера.' },
    closing_documents: { title: 'Закрывающие документы', why: 'Клиенту нужны закрывающие документы по заказу.' },
    analog_request: { title: 'Нужен аналог', why: 'Клиенту нужен подбор аналога, которого нет в прямой выдаче.' },
    exact_product_request: { title: 'Нужен именно этот товар', why: 'Клиент настаивает на конкретной позиции, которой нет в каталоге.' }
  };
  // группа в очереди «Ждут решения»: что решить менеджеру, коротко
  var GROUP = {
    quote_review: 'КП на отправку',
    quote_multi: 'КП на отправку',
    discount_over_limit: 'Скидка больше 5%',
    customer_request: 'Просят менеджера',
    needs_manager: 'Просят менеджера',
    server_license: 'Лицензия на сервер',
    price_confirmation: 'Уточнить цену',
    not_in_catalog: 'Нет в каталоге',
    catalog_unavailable: 'Нет в каталоге',
    exact_product_request: 'Нет в каталоге',
    analog_request: 'Нужен аналог',
    tender: 'Тендер и госзакупка',
    order_question: 'Вопросы по заказам',
    request_status: 'Вопросы по заказам',
    closing_documents: 'Вопросы по заказам',
    activation_problem: 'Активация и ключи',
    payment_question: 'Оплата и отсрочка',
    deferral: 'Оплата и отсрочка',
    complaint: 'Жалобы',
    model_routing: 'Другие запросы'
  };
  var ANSWER_EFFECT = 'Ответ уйдёт клиенту в этот же чат **от имени менеджера**, обращение закроется.';
  // срок ответа: агент обещает клиенту ответ менеджера через 2 минуты после последней реплики
  var ANSWER_MIN = 2;

  function requisites(q) { return [q.inn ? 'ИНН ' + q.inn : '', q.kpp ? 'КПП ' + q.kpp : ''].filter(Boolean).join(', '); }
  function sourceDate(s) { var d = s && new Date(s); return d && !isNaN(d) ? two(d.getDate()) + '.' + two(d.getMonth() + 1) + '.' + d.getFullYear() : ''; }

  // случай сервера {id, version, state, reason, quote, created, updated, first_client_message} → карточка кабинета
  function toCase(v) {
    var q = v.quote;
    var why = REASON[v.reason] || { title: v.reason_text || 'Запрос клиента', why: 'Агент передал разговор менеджеру.' };
    var who = q && q.customer ? q.customer : 'Посетитель сайта';
    var at = utc(v.updated || v.created);
    var c = {
      id: v.id, version: v.version, reason: v.reason, status: v.state === 'pending' ? 'waiting' : 'done',
      client: who, initials: initials(who), first: v.first_client_message || '',
      summary_facts: Array.isArray(v.summary_facts) ? v.summary_facts : [],
      deadline: at && !isNaN(Date.parse(at)) ? new Date(Date.parse(at) + ANSWER_MIN * 60000).toISOString() : null,
      steps: null, talk: null, talk_earlier: [], help_option: false, can_discount: false
    };
    if (q) {
      var offer = q.offer || {}, qty = q.quantity || 1, price = offer.price_kopecks != null ? offer.price_kopecks / 100 : (q.amount_kopecks || 0) / 100 / qty;
      c.kind = 'quote'; c.deadline_label = 'Отправить до'; c.group = 'КП на отправку';
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
      c.kind = 'answer'; c.deadline_label = 'Ответ до'; c.group = GROUP[v.reason] || v.reason_text || 'Другие запросы';
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
  // в ходе работы агента только живые слова: служебные названия событий, полей и причин наружу не выходят
  var HANDOFF = { not_in_catalog: 'товара нет в каталоге', model_routing: 'вопрос для человека' };
  var TOOL = { clarify_requirements: 'уточнил требования', search_catalog: 'искал в каталоге', check_registry: 'проверил реестр', draft_quote: 'собрал черновик КП', contact_manager: 'передал менеджеру' };
  var CLARIFY_FIELD = {
    focus: 'уточнил состав защиты',
    users: 'уточнил число пользователей',
    devices: 'уточнил число устройств',
    term: 'уточнил срок лицензии',
    deployment: 'уточнил способ развёртывания'
  };
  function stepText(e) {
    var d = e.detail || '';
    switch (e.event) {
      case 'opened': return 'клиент открыл чат';
      case 'catalog_search': return 'искал в каталоге';
      case 'registry_lookup': return 'проверил реестр';
      case 'quote_amount_calculated': return 'посчитал сумму ' + money(+d / 100);
      case 'price_calculated': return 'посчитал цену';
      case 'sent_to_manager': return d === 'quote_review' ? 'передал КП менеджеру на проверку' : 'передал менеджеру' + (HANDOFF[d] ? ': ' + HANDOFF[d] : REASON[d] ? ': ' + REASON[d].title.charAt(0).toLowerCase() + REASON[d].title.slice(1) : '');
      case 'document_prepared': return d === 'invoice' ? 'подготовил черновик счёта' : d === 'quote' ? 'подготовил КП' : '';
      case 'rule_applied': return 'применил правило по договору';
      case 'contract_rule_saved': return 'запомнил решение для договора';
      case 'product_comparison': return d === 'cryptopro_vipnet' ? 'сравнил КриптоПро и ViPNet' : 'сравнил продукты';
      case 'requirements_understood': return d === 'software_protection' ? 'понял: нужна защита ПО' : '';
      case 'demo_email_delivered': return 'отправил письмо на почту';
      case 'demo_email_failed': return 'письмо не ушло, нужен менеджер';
      case 'demo_coupon_offered': return 'предложил купон ' + d + '%';
      case 'model_unavailable': return 'модель не ответила, ответил по правилам';
      case 'model_budget_exceeded': return 'лимит модели потрачен, ответил по правилам';
      case 'manager_decision': return d === 'rejected' ? 'менеджер отказал' : 'менеджер ответил';
      case 'catalog_quote_sent': return 'КП ушло клиенту в чат';
      case 'knowledge_saved': return 'ответ менеджера сохранён в «Знаниях»';
      case 'knowledge_answer': return 'ответил из базы знаний';
      case 'model_tool_executed':
        if (d.indexOf('clarify_requirements:') === 0) return CLARIFY_FIELD[d.slice(21)] || TOOL.clarify_requirements;
        return TOOL[d] || '';
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
      var who = m.role === 'client' ? 'client' : m.role === 'manager' ? 'me' : 'agent';
      return { who: who, name: who === 'me' ? 'Антон' : undefined, text: (m.text || '') + (m.document_url ? ' Файл: ' + FILE_NAME : '') };
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
    // в карточке слова клиента стоят под заголовком, поэтому заголовок их не повторяет: агент вёл разговор сам
    if (!q && !REASON[v.reason]) c.title = 'Разговор с агентом';
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

  var MONTH_NOM = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
  var MONTH_CAP = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
  var MONTH_IN = ['за январь', 'за февраль', 'за март', 'за апрель', 'за май', 'за июнь', 'за июль', 'за август', 'за сентябрь', 'за октябрь', 'за ноябрь', 'за декабрь'];
  function group3(n) { return String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0'); }
  function decRu(n, d) { return (Math.round((n || 0) * Math.pow(10, d)) / Math.pow(10, d)).toFixed(d).replace('.', ','); }
  function formatCatalogDate(s) {
    if (!s) return '';
    var d = new Date(s.indexOf('T') >= 0 ? s : s.replace(' ', 'T'));
    if (isNaN(d)) return sourceDate(s) || s;
    return two(d.getDate()) + '.' + two(d.getMonth() + 1) + '.' + d.getFullYear() + ' в ' + two(d.getHours()) + ':' + two(d.getMinutes());
  }

  function knowledgeView() {
    return manager('GET', '/manager/knowledge').then(function (r) {
      var contractRules = (r.rules || []).map(function (rule, i) {
        return {
          id: 'cr-' + i,
          title: (rule.customer || 'Договор') + ': отсрочка ' + (rule.days || 0) + ' дн.',
          meta: 'Договор ' + (rule.contract_ref || '—'),
          text: rule.guidance || ''
        };
      });
      var savedAnswers = (r.answers || []).map(function (a) {
        var when = a.created ? sourceDate(utc(a.created)) : '';
        return {
          id: 'ans-' + a.id,
          title: a.question,
          meta: 'Ответ менеджера' + (when ? ', добавлен ' + when : ''),
          text: a.answer
        };
      });
      return {
        pending: [],
        gaps: [],
        fixes: [],
        rules: (r.agent_rules || []).concat(contractRules),
        articles: savedAnswers.concat(r.articles || []),
        readonly: true
      };
    });
  }

  var metricsPromise = null, metricsAt = 0;
  function loadMetrics() {
    var now = Date.now();
    if (!metricsPromise || now - metricsAt > 2000) {
      metricsAt = now;
      metricsPromise = manager('GET', '/manager/metrics').catch(function (e) { metricsPromise = null; throw e; });
    }
    return metricsPromise;
  }

  function agentStats() {
    return loadMetrics().then(function (m) {
      var now = new Date();
      var year = m.year || now.getFullYear();
      var monthIdx = m.month ? m.month - 1 : now.getMonth();
      var todayDay = m.day || now.getDate();
      var daysInMonth = m.days_in_month || 30;
      var dailyMap = m.daily_cost_rub || {};
      var days = [];
      for (var d = 1; d < todayDay; d++) days.push(+(dailyMap[String(d)] || dailyMap[d] || 0));
      var todayRub = +(m.today_cost_rub || 0);
      var spentRub = +((m.cost_microrubles || 0) / 1e6);
      var nonZero = days.filter(function (v) { return v > 0; });
      var forecastRub = nonZero.length
        ? nonZero.reduce(function (a, b) { return a + b; }, 0) / nonZero.length
        : todayRub;
      var legendPast = nonZero.length
        ? (Math.min.apply(null, nonZero) === Math.max.apply(null, nonZero)
            ? decRu(nonZero[0], 2) + ' ₽'
            : decRu(Math.min.apply(null, nonZero), 2) + '–' + decRu(Math.max.apply(null, nonZero), 2) + ' ₽')
        : '0 ₽';
      var totalTokens = (m.input_tokens || 0) + (m.output_tokens || 0);
      var per1k = totalTokens > 0 ? (spentRub / totalTokens) * 1000 : 0;
      var serverRub = m.server_rub != null ? m.server_rub : 370;
      var cat = m.catalog;
      var rawReasons = m.reasons || [];
      var reasons = rawReasons.length ? rawReasons : [
        { title: 'Черновик КП на проверку', count: 0 },
        { title: 'Сверить цену и количество', count: 0 },
        { title: 'Клиент просит менеджера', count: 0 },
        { title: 'Скидка больше 5%', count: 0 }
      ];
      var reasonsTotal = reasons.reduce(function (sum, x) { return sum + (x.count || 0); }, 0) || 1;
      var prevMonth = MONTH_CAP[(monthIdx + 11) % 12];
      return {
        sample: !!m.sample,
        budget_exceeded: !!m.budget_exceeded,
        month: MONTH_NOM[monthIdx] || 'ноябрь',
        month_in: MONTH_IN[monthIdx] || 'за ноябрь',
        year: year,
        month_index: monthIdx,
        requests: {
          total: m.cases || 0,
          today: m.today_cases || 0,
          closed: m.closed_by_agent || 0,
          handed: m.handed_to_manager || 0,
          unfinished: m.unfinished || 0
        },
        speed: [['Агент отвечает клиенту за', '1,07 с'], ['Менеджер отвечает в среднем за', '≈2 мин']],
        speed_note: 'Время агента замерено на стенде (медиана API), время менеджера назвал Softline.',
        days: days,
        today_day: todayDay,
        today_rub: todayRub,
        spent_rub: spentRub,
        forecast_rub: forecastRub,
        days_in_month: daysInMonth,
        legend_past: legendPast,
        spend_facts: [
          ['Вызовов модели', group3(m.model_calls || 0)],
          ['Токенов всего', group3(totalTokens)],
          ['Токенов сегодня', group3(m.today_tokens || 0)],
          ['Цена 1 000 токенов', totalTokens > 0 ? '≈' + decRu(per1k, 2) + ' ₽' : '0 ₽'],
          ['Сервер, в лимит не входит', money(serverRub) + ' в месяц']
        ],
        server_rub: serverRub,
        months: [{ name: prevMonth, requests: '0', closed: '0%', manager_time: '0 ч', agent: '0 ₽', total: '0 ₽' }],
        years: [year],
        health: [
          ['Чат на сайте', 'работает', 'ok'],
          ['Модель ' + (m.model_name || 'Alice AI LLM Flash'), m.model_configured ? 'работает' : 'правила без модели', m.model_configured ? 'ok' : ''],
          ['Каталог', cat && cat.source_date ? 'обновлён ' + formatCatalogDate(cat.source_date) : 'не загружен', cat && cat.offers ? 'ok' : 'fail'],
          ['В продаже с ценой', cat ? group3(cat.priced_available || 0) + ' из ' + group3(cat.offers || 0) : '0 из 0']
        ],
        outage: m.outages
          ? 'Зафиксировано сбоев модели: ' + m.outages + '. При сбое агент отвечает по правилам или передаёт менеджеру.'
          : 'Сбоев модели не зафиксировано (0).',
        reasons: reasons,
        reasons_total: reasonsTotal,
        reasons_note: m.sample ? 'По учебным обращениям для жюри.' : 'По фактическим передачам менеджеру из журнала стенда.',
        benefit: { minutes: 30, rate: 870, minutes_hint: 'Минут на обращение, по заданию 15–30', rate_hint: 'Час менеджера, ₽, подставьте свой' },
        benefit_note: 'Закрытые обращения берутся из журнала стенда, минуты и ставку можно менять на лету.'
      };
    });
  }

  function agentSettings() {
    return loadMetrics().then(function (m) {
      var limit = m.total_limit_rub != null ? Math.round(m.total_limit_rub) : 250;
      return {
        readonly: true,
        limit_rub: limit,
        warn_rub: Math.round(limit * 0.8),
        answer_min: 2,
        days: 'Пн–пт',
        from: '9:00',
        to: '18:00',
        notify: false,
        channel: 'telegram',
        channels: [
          { id: 'telegram', name: 'Telegram', note: 'бот магазина' },
          { id: 'max', name: 'MAX', note: 'нужна проверка компании', off: true }
        ],
        model: 'active',
        models: [
          { id: 'active', name: m.model_name || 'Модель стенда', cost: 'Оплата по токенам' }
        ],
        model_note: 'Токены и стоимость проверенных запросов видны в журнале.'
      };
    });
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
    if (method === 'GET' && path === '/agent/status') return manager('GET', '/manager/agent/status');
    if (method === 'POST' && path === '/agent/pause') return manager('POST', '/manager/agent/pause', body || {});
    if (method === 'GET' && path === '/agent/metrics') return loadMetrics();
    if (method === 'GET' && path === '/agent/stats') return agentStats();
    if (method === 'GET' && path === '/agent/settings') return agentSettings();
    if (method === 'GET' && path === '/cases') return casesList();
    if ((m = /^\/cases\/([^/]+)\/decision$/.exec(path))) return decide(decodeURIComponent(m[1]), body || {});
    if ((m = /^\/cases\/([^/]+)\/events$/.exec(path))) return events(decodeURIComponent(m[1]));
    if (method === 'GET' && path === '/journal') return journalList();
    if (method === 'GET' && path === '/knowledge') return knowledgeView();
    if (method === 'POST' && (path === '/jury/knowledge' || path === '/jury/knowledge/ask')) return manager(method, '/manager' + path, body);
    // правка скидки, чат менеджера с клиентом, возврат агенту, пауза и лимит, редактирование справки и настроек: в API пока нет
    return Promise.reject(fail(404));
  }

  function downloadCases(day) {
    var qs = '', filename = 'Журнал обращений.csv';
    if (day && !isNaN(day.getTime())) {
      var iso = day.getFullYear() + '-' + two(day.getMonth() + 1) + '-' + two(day.getDate());
      var ru = two(day.getDate()) + '.' + two(day.getMonth() + 1) + '.' + day.getFullYear();
      var tz = -day.getTimezoneOffset();
      qs = '?day=' + encodeURIComponent(iso) + '&tz_offset=' + encodeURIComponent(String(tz));
      filename = 'Журнал обращений, ' + ru + '.csv';
    }
    return fetch(API + '/manager/cases/export.csv' + qs, { credentials: 'same-origin', headers: managerHeaders() })
      .then(function (r) { if (!r.ok) throw fail(r.status); return r.blob(); })
      .then(function (blob) {
        var url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      });
  }

  window.SupportBackend = { call: call, downloadCases: downloadCases };
})();
