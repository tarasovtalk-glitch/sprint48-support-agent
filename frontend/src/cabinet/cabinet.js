/* Кабинет менеджера. Данные берёт с сервера агента (через api.js, контракт в корневом README), без ключей в браузере.
   ?demo или DEMO=1 при сборке: всё на примере данных из demo-data.js, действия меняют только эту страницу.
   Если сервер не отдаёт раздел, вкладка показывает пример и пишет об этом строкой сверху. */
(function () {
  'use strict';
  var CFG = window.SUPPORT_CONFIG || {};
  var DEMO = !!CFG.demo || /[?&]demo\b/.test(location.search);
  var API = String(CFG.apiBase || '/support/api').replace(/\/$/, '');
  var SAMPLE = window.CABINET_DEMO;

  /* ---------- мелочи ---------- */
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  function $(sel, root) { return (root || document).querySelector(sel); }
  function copy(v) { return v == null ? v : JSON.parse(JSON.stringify(v)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  // неразрывные пробелы: короткое слово держится за следующее, ₽ и % за число
  function ty(s) {
    s = String(s == null ? '' : s);
    for (var i = 0; i < 2; i++) s = s.replace(/(^|[\s(«])([А-Яа-яЁёA-Za-z0-9№≈]{1,3}) (?=\S)/g, '$1$2 ');
    return s.replace(/(\d) (?=\d{3}\b)/g, '$1 ').replace(/(\d) (₽|%|мин\b|ч\b)/g, '$1 $2');
  }
  function t(s) { return esc(ty(s)); }
  function money(n) { return ty(Math.round(n).toLocaleString('ru-RU').replace(/\s/g, ' ') + ' ₽'); }
  function rub(n) { return (Math.round(n * 100) / 100).toLocaleString('ru-RU', { minimumFractionDigits: n % 1 ? 2 : 0 }).replace(/\s/g, ' ') + ' ₽'; }
  function two(n) { return ('0' + n).slice(-2); }
  function hm(iso) { var d = iso ? new Date(iso) : new Date(); return isNaN(d) ? '' : d.getHours() + ':' + two(d.getMinutes()); }
  function hhmm(iso) { var d = iso ? new Date(iso) : new Date(); return isNaN(d) ? '' : two(d.getHours()) + ':' + two(d.getMinutes()); }
  function dayMonth(d) { return d.getDate() + ' ' + MONTHS[d.getMonth()]; }
  function plural(n, one, few, many) { var a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many; }
  function lcfirst(s) { s = String(s || ''); return s.charAt(0).toLowerCase() + s.slice(1); }
  function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }

  var IC = {
    chevron: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 6L8 10L12 6" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#393446"/></svg>',
    search: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M14.2 9A5.2 5.2 0 1 1 3.8 9a5.2 5.2 0 0 1 10.4 0Z" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#393446"/><path d="M13 13L16.2 16.2" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#393446"/></svg>',
    file: '<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M9 4.5H21.5L29 12V33.5H9V4.5Z" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#85828C"/><path d="M21.5 4.5V12H29" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#85828C"/><path d="M13.5 18H24.5M13.5 22H24.5M13.5 26H19" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#85828C"/><circle cx="30" cy="30" r="8" fill="#3E9A10"/><path d="M26.6 30.2L28.9 32.4L33.2 27.8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="white"/></svg>',
    download: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 3.5V12.5M14 8.5L10 12.5L6 8.5M4 16H16" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="#393446"/></svg>',
    pause: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M7.5 5V15M12.5 5V15" stroke-width="2" stroke-linecap="round" stroke="#393446"/></svg>',
    ok: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="8" fill="#3E9A10"/><path d="M4.8 8.2L7 10.4L11.2 5.8" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke="white"/></svg>',
    fail: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="8" fill="#A50F2D"/><path d="M5.6 5.6L10.4 10.4M10.4 5.6L5.6 10.4" stroke-width="1.6" stroke-linecap="round" stroke="white"/></svg>'
  };
  var BOT = '<img class="avatar avatar--24 avatar--bot" src="avatar-bot.svg" width="24" height="24" alt="">';

  function badge(tone, text) {
    var icon = tone === 'success' ? IC.ok : tone === 'danger' ? IC.fail : '';
    return '<span class="badge badge--' + tone + '">' + icon + t(text) + '</span>';
  }
  function counter(n, tone) { return '<span class="counter' + (tone ? ' counter--' + tone : '') + '">' + n + '</span>'; }
  function panelHead(title, right) { return '<div class="panel__head"><h2 class="t-h2">' + t(title) + '</h2>' + (right || '') + '</div>'; }
  function personAvatar(name) { return '<span class="avatar avatar--24" aria-hidden="true">' + esc((name || '?').charAt(0)) + '</span>'; }

  var toastTimer = 0;
  function toast(text) {
    var el = $('#toast'); el.textContent = text; el.classList.add('is-on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.classList.remove('is-on'); }, 2600);
  }

  /* ---------- данные ---------- */
  var store = { sample: {} };
  function call(method, path, body) {
    // живой API: запросы переводит api.js, экран остаётся тем же
    if (window.SupportBackend) return window.SupportBackend.call(method, path, body);
    return fetch(API + path, {
      method: method, credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      if (!r.ok) { var e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
      return r.status === 204 ? {} : r.json();
    });
  }
  // раздел с сервера; нет сервера или раздела, берём пример и помечаем вкладку
  function load(key, path, sample) {
    if (DEMO) { if (store[key] == null) store[key] = copy(sample); return Promise.resolve(store[key]); }
    return call('GET', path).then(function (d) { store.sample[key] = false; store[key] = d; return d; }, function () {
      store.sample[key] = true; if (store[key] == null) store[key] = copy(sample); return store[key];
    });
  }
  function isLocal(key) { return DEMO || store.sample[key]; }
  // действие: на сервер, а в примере только на странице
  function act(key, method, path, body, local) {
    if (isLocal(key)) { var r = local ? local() : null; return Promise.resolve(r); }
    return call(method, path, body).then(function (res) { if (local) local(res); return res; }, function (e) {
      toast('Не получилось сохранить: сервер агента не ответил'); throw e;
    });
  }

  /* ---------- состояние страницы ---------- */
  var ui = {
    tab: 'today', open: null, refusing: {}, history: {}, drafts: {}, ruleDone: {}, busy: {},
    jFilter: 'all', jQuery: '', jSel: null, jAll: false, jPeriod: 'today', jChannel: 'all',
    agentView: 'work', edit: null, aQuery: '', aAll: false, aOpen: null, gapOpen: null
  };

  function route() {
    var h = (location.hash || '#today').slice(1).split('/');
    ui.tab = ['today', 'journal', 'knowledge', 'agent'].indexOf(h[0]) >= 0 ? h[0] : 'today';
    if (ui.tab === 'journal' && h[1]) {
      if (h[1] === 'review' || h[1] === 'open' || h[1] === 'all') ui.jFilter = h[1]; else ui.jSel = decodeURIComponent(h[1]);
    }
    if (ui.tab === 'agent') ui.agentView = h[1] === 'settings' ? 'settings' : 'work';
    [].forEach.call(document.querySelectorAll('.tab'), function (a) {
      var on = a.getAttribute('data-tab') === ui.tab;
      a.classList.toggle('is-active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    render();
  }

  function render() {
    var v = $('#view');
    if (ui.tab === 'today') return loadToday().then(function () { v.innerHTML = viewToday(); after(); });
    if (ui.tab === 'journal') return load('journal', '/journal', SAMPLE.journal).then(function () { v.innerHTML = viewJournal(); after(); });
    if (ui.tab === 'knowledge') return load('knowledge', '/knowledge', SAMPLE.knowledge).then(function () { v.innerHTML = viewKnowledge(); after(); });
    return Promise.all([load('stats', '/agent/stats', SAMPLE.stats), load('settings', '/agent/settings', SAMPLE.settings)]).then(function () {
      v.innerHTML = viewAgent(); after();
    });
  }
  function after() { renderTop(); restoreDrafts(); scrollEdges(); }
  // «Как шёл разговор» открывается на последних репликах, как чат. Где переписка уходит за край окна,
  // край мягко гаснет: видно, что дальше есть ещё, а не что строку обрезали
  function scrollEdges() {
    [].forEach.call(document.querySelectorAll('.detail__scroll'), function (s) {
      if (!s._edges) { s._edges = true; s.scrollTop = s.scrollHeight; s.addEventListener('scroll', function () { edge(s); }, { passive: true }); }
      edge(s);
    });
  }
  function edge(s) {
    var more = s.scrollHeight - s.clientHeight > 1;
    s.classList.toggle('is-cut-top', more && s.scrollTop > 1);
    s.classList.toggle('is-cut-bottom', more && s.scrollTop + s.clientHeight < s.scrollHeight - 1);
  }

  function loadToday() { return load('cases', '/cases', SAMPLE.cases); }
  function cases() { return (store.cases && store.cases.cases) || []; }
  function waiting() { return cases().filter(function (c) { return c.status === 'waiting'; }); }

  /* ---------- шапка холста: счётчик, состояние агента, строка-предупреждение ---------- */
  function renderTop() {
    var n = waiting().length, c = $('#todayCounter');
    if (store.cases) { c.hidden = false; c.textContent = n; c.className = 'counter ' + (n ? 'counter--alert' : 'counter--zero'); }
    var st = (store.status && store.status.state) || 'on';
    var b = { on: ['success', 'Агент работает'], paused: ['warning', 'Агент на паузе'], limit: ['danger', 'Лимит потрачен'], down: ['danger', 'Агент не отвечает'] }[st] || ['success', 'Агент работает'];
    $('#agentBadge').innerHTML = badge(b[0], b[1]);
    var notes = [];
    if (st === 'limit') notes.push('<div class="notice"><span class="notice__text">' + t(store.status.text || 'Лимит на месяц потрачен. Агент молчит до 1-го числа, все чаты идут менеджерам') + '</span><a class="link" href="#agent/settings">Поднять лимит</a></div>');
    if (st === 'down') notes.push('<div class="notice"><span class="notice__text">' + t(store.status.text || 'Модель не отвечает. Все чаты идут менеджерам, агент вернётся сам, когда модель заработает') + '</span></div>');
    var key = { today: 'cases', journal: 'journal', knowledge: 'knowledge', agent: 'stats' }[ui.tab];
    if (!DEMO && store.sample[key]) {
      notes.push('<div class="notice notice--sample"><span class="notice__text">' + (key === 'cases'
        ? 'Нет связи с сервером агента. Пока показан пример, решения из него никуда не уходят'
        : 'Сервер агента пока не отдаёт этот раздел, показан пример с макета') + '</span></div>');
    }
    $('#notice').innerHTML = notes.join('');
    $('#notice').style.display = notes.length ? '' : 'none';
  }

  /* ---------- Сегодня ---------- */
  function viewToday() {
    var list = cases().slice().sort(function (a, b) {
      var wa = a.status === 'waiting' ? 0 : 1, wb = b.status === 'waiting' ? 0 : 1;
      if (wa !== wb) return wa - wb;
      return wa === 0 ? new Date(a.deadline) - new Date(b.deadline) : new Date(b.decided_at || 0) - new Date(a.decided_at || 0);
    });
    var w = waiting();
    if (ui.open == null && w.length) ui.open = w.slice().sort(function (a, b) { return new Date(a.deadline) - new Date(b.deadline); })[0].id;
    var main = '<section class="panel">' + panelHead('Ждут решения', counter(w.length, w.length ? 'alert' : 'zero')) + '<div class="panel__list">' +
      (list.length ? list.map(caseCard).join('') : '<div class="empty"><p class="empty__title">Сейчас решать нечего</p><p class="t-muted">' + t('Новый вопрос появится здесь, а ссылка на него придёт вам в Webim и на почту') + '</p></div>') +
      '</div></section>';
    var review = (store.cases && store.cases.review) || [];
    var today = (store.cases && store.cases.today) || null;
    var side = '<section class="panel">' + panelHead('На проверку', counter(review.length, review.length ? '' : 'zero')) + '<div class="panel__list">' +
      (review.length ? review.map(function (r) {
        return '<a class="row" href="#journal/' + encodeURIComponent(r.id) + '"><span class="row__main"><span class="row__title">' + t(r.title) + '</span><span class="row__meta">' + t(r.meta) + '</span></span></a>';
      }).join('') : '<p class="panel__note">Проверять нечего: клиенты довольны ответами агента</p>') + '</div></section>';
    if (today) {
      side += '<section class="today-agent"><p>' + t('Агент сегодня закрыл сам ' + today.closed + ' из ' + today.total + ' ' + plural(today.total, 'обращения', 'обращений', 'обращений') + (today.spent_rub != null ? ' и потратил на это ' + Math.round(today.spent_rub) + ' ₽' : '')) + '</p><a class="link" href="#agent">Статистика агента</a></section>';
    }
    return '<div class="columns"><div class="column">' + main + '</div><div class="column">' + side + '</div></div>';
  }

  function deadlineBadge(c) {
    if (!c.deadline) return ''; // срока ответа сервер может не прислать
    if (!DEMO && new Date(c.deadline) < new Date()) return badge('warning', 'Срок вышел в ' + hm(c.deadline));
    return badge('warning', 'Ответ до ' + hm(c.deadline));
  }
  function titleRow(c) {
    return '<div class="case__title-row"><p class="case__title">' + t(c.title) + '</p>' + (c.amount_rub != null ? '<p class="case__value">' + money(c.amount_rub) + '</p>' : '') + '</div>';
  }
  function historyLink(c) { return '<button class="link" type="button" data-act="history" data-id="' + esc(c.id) + '" aria-expanded="' + !!ui.history[c.id] + '">Как шёл разговор</button>'; }
  function historyBlock(c) {
    if (!ui.history[c.id]) return '';
    if (!c.events) return '<div class="case__history"><p class="t-muted">Загружаю переписку…</p></div>';
    return '<div class="case__history">' + eventsHtml(c.events) + '</div>';
  }
  function draft(c) { return ui.drafts[c.id] || (ui.drafts[c.id] = {}); }

  function caseCard(c) {
    var id = esc(c.id), busy = ui.busy[c.id] ? ' is-busy' : '';
    // решённый случай
    if (c.status !== 'waiting') {
      var by = c.decided_by && c.decided_by !== 'Вы' && c.decided_by !== 'me' ? c.decided_by + ' в ' : 'в ';
      var b = c.status === 'approved' ? badge('success', 'Согласовано') : c.status === 'answered' ? badge('success', 'Ответ отправлен') : badge('neutral', 'Отказано');
      var h = '<article class="case' + busy + '" data-id="' + id + '"><div class="case__head"><div class="case__top">' + b +
        '<span class="case__meta">' + t(by + hm(c.decided_at)) + '</span><span class="case__top-right">' + historyLink(c) + '</span></div>' +
        titleRow(c) + '<p class="case__desc">' + t(c.result || '') + '</p></div>';
      if (c.status === 'approved' && c.rule && !ui.ruleDone[c.id]) h += ruleBlock(c);
      return h + historyBlock(c) + '</article>';
    }
    var open = ui.open === c.id;
    if (!open) {
      var desc = c.kind === 'answer' || !c.advice ? c.desc : 'Совет агента: ' + lcfirst(c.advice);
      return '<article class="case is-collapsed' + busy + '" data-act="open" data-id="' + id + '" tabindex="0" role="button" aria-expanded="false"><div class="case__head"><div class="case__top">' + deadlineBadge(c) +
        '<span class="case__top-right"><span class="case__toggle">' + IC.chevron + '</span></span></div>' + titleRow(c) + '<p class="case__desc">' + t(desc) + '</p></div></article>';
    }
    var head = '<div class="case__head"><div class="case__top">' + deadlineBadge(c) + '<span class="case__top-right">' + historyLink(c) +
      '<button class="case__toggle" type="button" data-act="collapse" data-id="' + id + '" aria-label="Свернуть">' + IC.chevron + '</button></span></div>' + titleRow(c);
    var body;
    if (c.kind === 'answer') body = answerBlock(c);
    else if (ui.refusing[c.id]) body = refuseBlock(c);
    else body = adviceBlock(c);
    var descText = ui.refusing[c.id] ? 'Совет агента: ' + (c.recommend === 'refuse' ? 'отказать' : 'согласовать') : c.desc;
    return '<article class="case is-open' + busy + '" data-id="' + id + '">' + head + '<p class="case__desc">' + t(descText) + '</p></div>' + body + historyBlock(c) + '</article>';
  }

  function adviceBlock(c) {
    var approve = '<button class="btn ' + (c.recommend === 'refuse' ? 'btn--secondary' : 'btn--primary') + '" type="button" data-act="approve" data-id="' + esc(c.id) + '">' + t(c.approve_label || 'Согласовать') + '</button>';
    var refuse = '<button class="btn ' + (c.recommend === 'refuse' ? 'btn--primary' : 'btn--secondary') + '" type="button" data-act="refuse" data-id="' + esc(c.id) + '">Отказать</button>';
    return '<div class="case__block">' + (c.advice ? '<div class="case__advice-head">' + BOT + 'Совет агента</div><p>' + t(c.advice) + '</p>' : '') +
      (c.effect ? '<div class="case__effect"><p class="case__effect-title">' + (c.recommend === 'refuse' ? 'Если согласовать, агент' : 'Что сделает агент') + '</p><p>' + t(c.effect) + '</p></div>' : '') +
      '<div class="case__buttons">' + (c.recommend === 'refuse' ? refuse + approve : approve + refuse) + '</div></div>';
  }

  function refuseBlock(c) {
    var d = draft(c), reasons = (c.refuse_reasons || []).concat(['Другая причина']);
    if (d.reason == null) d.reason = reasons[0];
    if (d.reply == null) d.reply = replyFor(c, d.reason);
    return '<div class="case__block"><p class="case__block-title" id="reasons-' + esc(c.id) + '">Причина отказа</p><div class="radios" role="radiogroup" aria-labelledby="reasons-' + esc(c.id) + '">' +
      reasons.map(function (r) {
        return '<label class="radio"><input type="radio" name="reason-' + esc(c.id) + '" value="' + esc(r) + '" data-draft="reason" data-id="' + esc(c.id) + '"' + (d.reason === r ? ' checked' : '') + '>' + t(r) + '</label>';
      }).join('') + '</div>' +
      '<label class="case__effect"><span class="case__block-title">' + t('Что агент ответит клиенту, текст можно поправить') + '</span><textarea class="textarea" rows="3" data-draft="reply" data-id="' + esc(c.id) + '">' + esc(d.reply) + '</textarea></label>' +
      '<div class="case__buttons"><button class="btn btn--primary" type="button" data-act="refuse-send" data-id="' + esc(c.id) + '">Отказать и ответить клиенту</button>' +
      '<button class="btn btn--secondary" type="button" data-act="refuse-back" data-id="' + esc(c.id) + '">Назад</button></div></div>';
  }
  function replyFor(c, reason) { return (c.refuse_replies && c.refuse_replies[reason]) || (reason === 'Другая причина' ? '' : c.refuse_reply || ''); }

  function answerBlock(c) {
    var d = draft(c);
    if (d.reply == null) d.reply = c.reply_draft || '';
    if (d.help == null) d.help = c.help_option !== false; // переключатель «в справку» только там, где сервер это умеет
    return '<div class="case__block"><div class="case__advice-head">' + BOT + 'Сводка агента</div><p>' + t(c.advice) + '</p>' +
      '<label class="case__effect"><span class="case__block-title">Ответ для клиента</span><textarea class="textarea" rows="2" data-draft="reply" data-id="' + esc(c.id) + '" placeholder="Что передать клиенту">' + esc(d.reply) + '</textarea></label>' +
      (c.help_option === false ? '' : '<label class="switch"><input type="checkbox" data-draft="help" data-id="' + esc(c.id) + '"' + (d.help ? ' checked' : '') + '>' + t('Добавить ответ в справку, в следующий раз агент ответит сам') + '</label>') +
      (c.effect ? '<div class="case__effect"><p class="case__effect-title">Что сделает агент</p><p>' + t(c.effect) + '</p></div>' : '') +
      '<div class="case__buttons"><button class="btn btn--primary" type="button" data-act="answer" data-id="' + esc(c.id) + '"' + (d.reply.trim() ? '' : ' disabled') + '>Ответить клиенту</button></div></div>';
  }

  function ruleBlock(c) {
    var d = draft(c); d.rule = d.rule || copy(c.rule.params || {});
    var parts = (c.rule.text || []).map(function (p) {
      var m = /^\{(\w+)\}$/.exec(p);
      if (!m) return '<span>' + t(p) + '</span>';
      var v = d.rule[m[1]];
      var w = String(v == null ? '' : v.toLocaleString ? v.toLocaleString('ru-RU') : v).length;
      return '<input class="input" inputmode="numeric" size="' + Math.max(2, w) + '" style="width:' + (Math.max(2, w) * 9 + 22) + 'px" aria-label="Число в правиле" data-draft="rule" data-key="' + m[1] + '" data-id="' + esc(c.id) + '" value="' + esc(v == null ? '' : Number(v).toLocaleString('ru-RU').replace(/\s/g, ' ')) + '">';
    }).join('');
    return '<div class="case__block"><p class="case__block-title">Сделать правилом?</p><div class="case__rule">' + parts + '</div>' +
      '<p class="t-muted">' + t('Такие просьбы агент будет согласовывать сам и записывать в журнал. Числа можно изменить') + '</p>' +
      '<div class="case__buttons case__buttons--rule"><button class="btn btn--secondary" type="button" data-act="rule" data-id="' + esc(c.id) + '">Сделать правилом</button>' +
      '<button class="link" type="button" data-act="rule-later" data-id="' + esc(c.id) + '">Не сейчас</button></div></div>';
  }

  function eventsHtml(list) {
    return '<div class="events">' + (list || []).map(function (e) {
      var who = e.actor === 'agent' ? BOT + '<span class="event__name">Агент</span>' : personAvatar(e.name) + '<span class="event__name">' + t(e.name || (e.actor === 'manager' ? 'Менеджер' : 'Клиент')) + '</span>';
      return '<div class="event"><div class="event__head">' + who + '<span class="event__time">' + hhmm(e.time) + '</span></div><p>' + t(e.text) + '</p>' +
        (e.source ? '<p class="event__source">' + t(e.source) + '</p>' : '') + (e.steps ? '<p class="event__steps">' + t(e.steps) + '</p>' : '') + '</div>';
    }).join('') + '</div>';
  }

  function findCase(id) { return cases().filter(function (c) { return c.id === id; })[0]; }
  function replaceCase(updated) {
    var list = cases();
    for (var i = 0; i < list.length; i++) if (list[i].id === updated.id) { var keep = list[i].events; list[i] = updated; if (!updated.events && keep) updated.events = keep; }
  }
  function decide(c, body, local) {
    ui.busy[c.id] = true; render();
    return act('cases', 'POST', '/cases/' + encodeURIComponent(c.id) + '/decision', body, function (res) {
      if (res && res.id) replaceCase(res); else local();
    }).then(function () {
      delete ui.busy[c.id]; delete ui.refusing[c.id];
      var next = waiting()[0]; ui.open = next ? next.id : null;
      render();
    }, function () { delete ui.busy[c.id]; render(); });
  }

  /* ---------- Журнал ---------- */
  function jItems() { return (store.journal && store.journal.items) || []; }
  function jTime(it) {
    if (it.time) return new Date(it.time);
    var m = /(\d{1,2}):(\d{2})\s*$/.exec(it.meta || ''); var d = new Date();
    if (m) d.setHours(+m[1], +m[2], 0, 0); return d;
  }
  function jChannel(it) { if (it.channel) return it.channel; var m = / · (чат|почта|звонок) · /.exec(it.meta || ''); return m ? m[1] : ''; }
  function jScope(list) {
    var now = new Date(), y = new Date(); y.setDate(y.getDate() - 1);
    var wk = new Date(); wk.setDate(wk.getDate() - 7);
    return list.filter(function (it) {
      var d = jTime(it);
      if (ui.jPeriod === 'today' && !sameDay(d, now)) return false;
      if (ui.jPeriod === 'yesterday' && !sameDay(d, y)) return false;
      if (ui.jPeriod === 'week' && d < wk) return false;
      if (ui.jChannel !== 'all' && jChannel(it) !== ui.jChannel) return false;
      return true;
    });
  }
  function viewJournal() {
    var scoped = jScope(jItems());
    var counts = { all: scoped.length, open: scoped.filter(function (i) { return i.open; }).length, review: scoped.filter(function (i) { return i.review; }).length };
    var q = ui.jQuery.trim().toLowerCase();
    var list = scoped.filter(function (it) {
      if (ui.jFilter === 'open' && !it.open) return false;
      if (ui.jFilter === 'review' && !it.review) return false;
      return !q || (it.title + ' ' + it.meta + ' ' + (it.client || '') + ' ' + (it.inn || '')).toLowerCase().indexOf(q) >= 0;
    });
    var PAGE = 6, shown = ui.jAll ? list : list.slice(0, PAGE);
    if (!ui.jSel || !list.some(function (i) { return i.id === ui.jSel; })) ui.jSel = list.length ? list[0].id : null;
    var chip = function (key, label) { return '<button class="chip' + (ui.jFilter === key ? ' is-active' : '') + '" type="button" data-act="jfilter" data-key="' + key + '" aria-pressed="' + (ui.jFilter === key) + '">' + label + counter(counts[key]) + '</button>'; };
    var today = new Date();
    var sel = function (name, val, opts) {
      return '<label class="select"><span class="sr">' + name + '</span><select data-act="jscope" data-key="' + name + '">' + opts.map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === val ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join('') + '</select>' + IC.chevron + '</label>';
    };
    var main = '<section class="panel">' + panelHead('Журнал') +
      '<div class="journal__tools"><div class="chips">' + chip('all', 'Все') + chip('open', 'Не закрыты') + chip('review', 'Проверить') + '</div>' +
      '<label class="field">' + IC.search + '<input type="search" data-act="jsearch" placeholder="Клиент, ИНН или № заказа" aria-label="Поиск по журналу" value="' + esc(ui.jQuery) + '"></label></div>' +
      '<div class="journal__scope">' + sel('period', ui.jPeriod, [['today', 'Сегодня, ' + dayMonth(today)], ['yesterday', 'Вчера'], ['week', 'За неделю'], ['all', 'Всё время']]) +
      sel('channel', ui.jChannel, [['all', 'Все каналы'], ['чат', 'Чат'], ['почта', 'Почта'], ['звонок', 'Звонки']]) + '</div>' +
      '<div class="panel__list">' + (shown.length ? shown.map(jRow).join('') : '<p class="panel__note">' + (q ? 'Ничего не нашлось. Попробуйте название компании, ИНН или номер заказа' : ui.jFilter === 'review' ? 'Проверять нечего' : 'Разговоров за этот период нет') + '</p>') + '</div>' +
      (ui.jFilter === 'review' && list.length ? '<p class="panel__note">Разговор уйдёт из списка после вашей проверки</p>'
        : list.length > shown.length ? '<button class="link" type="button" data-act="jmore">Показать ещё ' + (list.length - shown.length) + '</button>' : '') +
      '</section>';
    var it = jItems().filter(function (i) { return i.id === ui.jSel; })[0];
    return '<div class="columns"><div class="column">' + main + '</div><div class="column">' + (it ? jDetail(it) : '') + '</div></div>';
  }
  function jRow(it) {
    var side = '';
    if (it.deadline && it.open) side = '<span class="row__side row__side--alert">' + (it.value_rub != null ? '<span class="row__value">' + money(it.value_rub) + '</span>' : '') + badge('warning', 'Ответ до ' + hm(it.deadline)) + '</span>';
    else if (it.value_rub != null) side = '<span class="row__side"><span class="row__value">' + money(it.value_rub) + '</span>' + (it.status ? '<span class="row__status">' + t(it.status) + '</span>' : '') + '</span>';
    else if (it.status) side = '<span class="row__side"><span class="row__status">' + t(it.status) + '</span></span>';
    return '<button class="row' + (it.id === ui.jSel ? ' is-selected' : '') + '" type="button" data-act="jselect" data-id="' + esc(it.id) + '" aria-pressed="' + (it.id === ui.jSel) + '"><span class="row__main"><span class="row__title">' + t(it.title) + '</span><span class="row__meta">' + t(it.meta) + '</span></span>' + side + '</button>';
  }
  function jDetail(it) {
    if (!DEMO && !store.sample.journal && !it.events && !it._loading) {
      it._loading = true;
      call('GET', '/journal/' + encodeURIComponent(it.id)).then(function (d) { Object.assign(it, d); it._loading = false; if (ui.tab === 'journal') render(); }, function () { it._loading = false; it.events = []; });
    }
    var reviewing = it.review;
    var h = '<section class="detail"><div class="detail__head"><h2 class="t-h2">' + t(it.detail_title || it.title) + '</h2><p class="t-muted">' + t(it.client || '') + '</p></div>';
    h += '<div class="detail__now">' + (it.badge ? badge(it.badge.tone || 'neutral', it.badge.text) : '') + (it.next ? '<p class="t-muted">' + t(it.next) + '</p>' : '') +
      (it.file ? '<a class="file-row"' + (it.file.url ? ' href="' + esc(it.file.url) + '" target="_blank" rel="noopener"' : '') + '>' + IC.file + '<span class="file-row__text"><span class="file-row__name">' + t(it.file.name) + '</span><span class="file-row__note">' + t(it.file.note || '') + '</span></span>' + (it.file.url ? IC.download : '') + '</a>' : '') +
      (it.sent ? '<p class="t-muted">' + t(it.sent) + '</p>' : '') + '</div>';
    h += '<div class="detail__history"><p class="t-title">Как шёл разговор</p><div class="detail__scroll' + (reviewing ? ' detail__scroll--all' : '') + '" tabindex="0" aria-label="Переписка">' +
      (it.events ? eventsHtml(it.events) : '<p class="t-muted">Загружаю переписку…</p>') + '</div></div>';
    if (reviewing) {
      var d = ui.drafts['j-' + it.id] || (ui.drafts['j-' + it.id] = { fix: '' });
      h += '<div class="detail__review"><label class="case__effect"><span class="case__block-title">Как надо было ответить</span><textarea class="textarea" rows="2" data-draft="fix" data-id="j-' + esc(it.id) + '" placeholder="Например: клиент уже назвал срок лицензии, не переспрашивать">' + esc(d.fix) + '</textarea></label>' +
        '<p class="t-muted">' + t('Агент запомнит поправку, она появится в «Знаниях»') + '</p><div class="detail__actions">' +
        '<button class="btn btn--primary" type="button" data-act="jfix" data-id="' + esc(it.id) + '"' + (d.fix.trim() ? '' : ' disabled') + '>Сохранить поправку</button>' +
        '<button class="link" type="button" data-act="jok" data-id="' + esc(it.id) + '">Агент ответил верно</button></div></div>';
    }
    // расход модели по журналу обращения: число вызовов и рубли с НДС, мелкие суммы до десятитысячных
    if (it.model_calls != null) {
      var spent = it.model_calls ? it.model_calls + ' ' + plural(it.model_calls, 'вызов', 'вызова', 'вызовов') + ', ' +
        (Math.round(it.model_cost_rub * 10000) / 10000).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' ₽ с НДС'
        : 'не вызывалась, ответы по правилам и каталогу';
      h += '<div class="detail__cost"><span class="fact"><span class="fact__label">Модель</span><span class="fact__value">' + t(spent) + '</span></span></div>';
    } else if (it.cost_rub != null || it.manager_min != null) {
      h += '<div class="detail__cost">' + (it.cost_rub != null ? '<span class="fact"><span class="fact__label">Работа агента</span><span class="fact__value">' + rub(it.cost_rub) + '</span></span>' : '') +
        (it.manager_min != null ? '<span class="fact"><span class="fact__label">Время менеджера</span><span class="fact__value">' + it.manager_min + ' мин</span></span>' : '') + '</div>';
    }
    return h + '</section>';
  }
  function reviewed(id) {
    jItems().forEach(function (i) { if (i.id === id) i.review = false; });
    if (store.cases && store.cases.review) store.cases.review = store.cases.review.filter(function (r) { return r.id !== id; });
  }

  /* ---------- Знания ---------- */
  function actionRow(r, linkAct, linkText, extra) {
    return '<div class="row"><span class="row__main"><span class="row__title">' + t(r.title) + '</span><span class="row__meta">' + t(r.meta) + '</span></span>' +
      '<button class="link row__action" type="button" data-act="' + linkAct + '" data-id="' + esc(r.id) + '">' + linkText + '</button></div>' + (extra || '');
  }
  function viewKnowledge() {
    var k = store.knowledge || {};
    var pending = k.pending || [], rules = k.rules || [], arts = k.articles || [], gaps = k.gaps || [], fixes = k.fixes || [];
    var q = ui.aQuery.trim().toLowerCase();
    var found = arts.filter(function (a) { return !q || (a.title + ' ' + (a.text || '')).toLowerCase().indexOf(q) >= 0; });
    var shown = ui.aAll || q ? found : found.slice(0, 5);
    var main = '';
    main += '<section class="panel">' + panelHead('Ждут добавления в справку', counter(pending.length, pending.length ? '' : 'zero')) + '<div class="panel__list panel__list--tight">' +
      (pending.length ? pending.map(function (p) { return actionRow(p, 'k-add', 'Добавить в справку'); }).join('') : '<p class="panel__note">' + t('Новых ответов менеджеров для справки нет') + '</p>') + '</div></section>';
    main += '<section class="panel">' + panelHead('Правила агента', counter(rules.filter(function (r) { return !r.off; }).length)) + '<div class="panel__list panel__list--tight">' +
      (rules.length ? rules.map(function (r) { return actionRow(r, 'k-rule', r.off ? 'Включить' : 'Выключить'); }).join('') : '<p class="panel__note">' + t('Правил пока нет. Решение в карточке можно сделать правилом') + '</p>') + '</div></section>';
    main += '<section class="panel">' + panelHead('Статьи справки', counter(k.articles_total && !isLocal('knowledge') ? k.articles_total : arts.length)) +
      '<label class="field" style="max-width:none">' + IC.search + '<input type="search" data-act="asearch" placeholder="Тема или слово из статьи" aria-label="Поиск по справке" value="' + esc(ui.aQuery) + '"></label>' +
      '<div class="panel__list panel__list--tight">' + (shown.length ? shown.map(function (a) {
        return actionRow(a, 'a-open', ui.aOpen === a.id ? 'Свернуть' : 'Открыть', ui.aOpen === a.id ? articleEditor(a) : '');
      }).join('') : '<p class="panel__note">Ничего не нашлось</p>') + '</div>' +
      (!q && found.length > shown.length ? '<button class="link" type="button" data-act="amore">Показать ещё ' + (found.length - shown.length) + '</button>' : '') + '</section>';
    var side = '<section class="panel">' + panelHead('Где агенту не хватает ответов') + '<div class="panel__list panel__list--tight">' +
      (gaps.length ? gaps.map(function (g) { return actionRow(g, 'g-open', ui.gapOpen === g.id ? 'Свернуть' : 'Дописать справку', ui.gapOpen === g.id ? gapEditor(g) : ''); }).join('') : '<p class="panel__note">Пробелов в справке не видно</p>') + '</div></section>';
    side += '<section class="panel">' + panelHead('Поправки из проверок', counter(fixes.length, fixes.length ? '' : 'zero')) + '<div class="panel__list panel__list--tight">' +
      (fixes.length ? fixes.map(function (f) { return actionRow(f, 'f-del', 'Убрать'); }).join('') : '<p class="panel__note">' + t('Поправок нет. Их добавляют в журнале при проверке разговора') + '</p>') + '</div></section>';
    return '<div class="columns"><div class="column">' + main + '</div><div class="column">' + side + '</div></div>';
  }
  function articleEditor(a) {
    var d = ui.drafts['a-' + a.id] || (ui.drafts['a-' + a.id] = { text: a.text || '' });
    return '<div class="row" style="flex-direction:column;align-items:stretch;gap:12px"><textarea class="textarea" rows="4" data-draft="text" data-id="a-' + esc(a.id) + '" aria-label="Текст статьи «' + esc(a.title) + '»" placeholder="Текст статьи, по нему отвечает агент">' + esc(d.text) + '</textarea>' +
      '<div class="detail__actions"><button class="btn btn--primary" type="button" data-act="a-save" data-id="' + esc(a.id) + '">Сохранить статью</button></div></div>';
  }
  function gapEditor(g) {
    var d = ui.drafts['g-' + g.id] || (ui.drafts['g-' + g.id] = { text: '' });
    return '<div class="row" style="flex-direction:column;align-items:stretch;gap:12px"><textarea class="textarea" rows="4" data-draft="text" data-id="g-' + esc(g.id) + '" aria-label="Новая статья: ' + esc(g.title) + '" placeholder="Что агент должен отвечать на такие вопросы">' + esc(d.text) + '</textarea>' +
      '<div class="detail__actions"><button class="btn btn--primary" type="button" data-act="g-save" data-id="' + esc(g.id) + '"' + (d.text.trim() ? '' : ' disabled') + '>Добавить в справку</button></div></div>';
  }
  function byId(list, id) { return (list || []).filter(function (x) { return x.id === id; })[0]; }
  function without(list, id) { return (list || []).filter(function (x) { return x.id !== id; }); }

  /* ---------- Агент ---------- */
  function viewAgent() {
    var st = (store.status && store.status.state) || 'on';
    var paused = st === 'paused';
    var head = '<div class="agent__head"><div class="chips">' +
      '<a class="chip chip--plain' + (ui.agentView === 'work' ? ' is-active' : '') + '" href="#agent"' + (ui.agentView === 'work' ? ' aria-current="page"' : '') + '>Работа</a>' +
      '<a class="chip chip--plain' + (ui.agentView === 'settings' ? ' is-active' : '') + '" href="#agent/settings"' + (ui.agentView === 'settings' ? ' aria-current="page"' : '') + '>Настройки</a></div>' +
      '<div class="agent__pause">' + (paused
        ? '<span>' + t('Вы поставили паузу ' + (store.status.since ? 'сегодня в ' + hm(store.status.since) : '') + '. Все обращения идут менеджерам, как до агента').replace(' .', '.') + '</span><button class="btn btn--primary" type="button" data-act="pause" data-on="0">Включить агента</button>'
        : '<span>' + t('На паузе все обращения идут менеджерам, как до агента') + '</span><button class="btn btn--secondary btn--icon-left" type="button" data-act="pause" data-on="1">' + IC.pause + 'Поставить на паузу</button>') +
      '</div></div>';
    return '<div style="display:flex;flex-direction:column;gap:28px">' + head + (ui.agentView === 'settings' ? viewSettings() : viewWork()) + '</div>';
  }
  function viewWork() {
    var s = store.stats || {}, set = store.settings || {};
    var w = waiting().length, rv = ((store.cases && store.cases.review) || []).length;
    var tiles = (s.tiles || []).map(function (tl) {
      var link = tl.link;
      if (link && link.href === '#today' && store.cases) link = { href: '#today', text: w ? w + ' ' + plural(w, 'ждёт', 'ждут', 'ждут') + ' вашего решения' : 'Решать нечего' };
      if (link && link.href === '#journal/review' && store.cases) link = { href: '#journal/review', text: rv ? rv + ' ' + plural(rv, 'ждёт', 'ждут', 'ждут') + ' вашей проверки' : 'Проверять нечего' };
      return '<section class="tile"><p class="t-title">' + t(tl.title) + '</p><div class="tile__figures"><div class="tile__figure"><span class="t-number">' + t(tl.month) + '</span><span class="t-muted">за ' + esc(s.month || 'месяц') + '</span></div><span class="tile__divider"></span>' +
        '<div class="tile__figure"><span class="t-number">' + t(tl.today) + '</span><span class="t-muted">сегодня</span></div></div>' +
        (link ? '<a class="link" href="' + esc(link.href) + '">' + t(link.text) + '</a>' : tl.note ? '<p class="tile__note">' + t(tl.note) + '</p>' : '') + '</section>';
    }).join('');
    var h = '<div class="stats">' + tiles + '</div>';
    h += '<div class="columns"><div class="column"><section class="panel">' + panelHead('Работа агента по дням, ' + (s.month || '')) + chart(s) + '</section></div>';
    var sp = s.spend || {}, limit = set.limit_rub || sp.limit || 0, warn = set.warn_rub || sp.warn || 0;
    var pct = limit ? Math.min(100, (sp.spent || 0) / limit * 100) : 0;
    h += '<div class="column"><section class="panel">' + panelHead('Лимит на работу агента, ' + (s.month || '')) +
      '<div class="spend"><div class="spend__total"><span class="t-number">' + money(sp.spent || 0) + '</span><span class="t-lead t-muted">из ' + money(limit) + '</span></div>' +
      '<div class="meter" role="img" aria-label="' + esc('Потрачено ' + Math.round(pct) + '% лимита') + '"><span class="meter__track"></span><span class="meter__spent" style="width:' + pct + '%"></span>' + (warn && limit ? '<span class="meter__threshold" style="left:calc(' + (warn / limit * 100) + '% - 1px)"></span>' : '') + '</div>' +
      (sp.forecast ? '<p>' + t(sp.forecast) + '</p>' : '') + '</div>' +
      (warn ? '<p>' + t('При ' + money(warn) + ' письмо получат менеджеры и бухгалтерия') + '</p>' : '') +
      '<p>' + t('При ' + money(limit) + ' агент замолкает до 1 ' + nextMonth() + ', чат идёт менеджерам') + '</p></section></div></div>';
    var topics = s.topics || [], max = Math.max.apply(null, topics.map(function (x) { return x.share; }).concat([1]));
    h += '<div class="columns"><div class="column"><section class="panel">' + panelHead('О чём спрашивают, ' + (s.month || '')) + '<div class="panel__list panel__list--tight">' +
      topics.map(function (tp) {
        return '<div class="topic"><div class="topic__top"><span class="topic__title">' + t(tp.title) + '</span><span class="topic__count">' + tp.count + '</span><span class="topic__share">' + tp.share + '%</span></div>' +
          '<div class="topic__track"><div class="topic__fill" style="width:' + (tp.share / max * 100) + '%"></div></div>' +
          (tp.note ? '<p class="topic__note">' + t(tp.note) + '</p>' : '') + (tp.link ? '<a class="link" href="#knowledge">' + t(tp.link) + '</a>' : '') + '</div>';
      }).join('') + '</div></section></div>';
    var cn = s.connections || { ok: true, text: '' };
    h += '<div class="column"><section class="panel">' + panelHead('Сбои за ' + (s.month || 'месяц')) +
      '<div class="connections">' + (cn.ok ? IC.ok : IC.fail) + '<p>' + t(cn.text) + '</p></div><div class="panel__list panel__list--tight">' +
      (s.outages || []).map(function (o) { return '<div class="row"><span class="row__main"><span class="row__title">' + t(o.title) + '</span><span class="row__meta">' + t(o.meta) + '</span></span></div>'; }).join('') +
      '</div><p class="panel__note">' + t('При сбое чат сразу уходит менеджерам, клиент не остаётся без ответа') + '</p></section></div></div>';
    if ((s.months || []).length) {
      h += '<section class="panel">' + panelHead('Прошлые месяцы') + '<div class="months">' + s.months.map(function (m) {
        return '<div class="month"><p class="t-title">' + t(m.name) + '</p><div class="month__total"><span class="t-number">' + t(m.total) + '</span><span class="t-muted">всего за месяц</span></div><div class="month__divider"></div>' +
          '<div class="month__facts">' + m.facts.map(function (f) { return '<span class="fact"><span class="fact__label">' + t(f[0]) + '</span><span class="fact__value">' + t(f[1]) + '</span></span>'; }).join('') + '</div></div>';
      }).join('') + '</div></section>';
    }
    return h;
  }
  function nextMonth() { var d = new Date(); return MONTHS[(d.getMonth() + 1) % 12]; }
  function chart(s) {
    var n = s.days_in_month || 30, past = s.days || [], today = s.today_day || past.length + 1;
    var vals = [];
    for (var i = 1; i <= n; i++) vals.push(i < today ? past[i - 1] || 0 : i === today ? s.today_rub || 0 : s.forecast_rub || 0);
    var top = Math.max(30, Math.ceil(Math.max.apply(null, vals) / 10) * 10 - (Math.max.apply(null, vals) > 30 && Math.max.apply(null, vals) <= 33 ? 10 : 0));
    var px = 135 / top; // 135 px от нуля до верхней линии, как в макете
    var grid = [top, top * 2 / 3, top / 3, 0].map(function (v, k) {
      var y = 23 + k * 45;
      return '<span class="chart__grid" style="top:' + y + 'px"></span><span class="chart__y" style="top:' + y + 'px">' + (v ? Math.round(v) + ' ₽' : '0') + '</span>';
    }).join('');
    var bars = vals.map(function (v, k) {
      var d = k + 1, cls = d < today ? '' : d === today ? ' chart__bar--today' : ' chart__bar--future';
      return '<span class="chart__bar' + cls + '" style="height:' + Math.min(150, Math.round(v * px)) + 'px" title="' + d + ' ' + esc(MONTHS[new Date().getMonth()]) + ': ' + Math.round(v) + ' ₽' + (d > today ? ', прогноз' : '') + '"></span>';
    }).join('');
    var marks = [1, 5, 10, 15, 20, today, n].filter(function (v, k, a) { return a.indexOf(v) === k && (v === today || Math.abs(v - today) > 2); });
    var xs = marks.map(function (d) { return '<span' + (d === today ? ' class="is-today"' : '') + ' style="left:' + ((d - 0.5) / n * 100) + '%">' + d + '</span>'; }).join('');
    return '<div class="chart"><div class="chart__plot" role="img" aria-label="' + esc('Расход агента по дням: сегодня ' + Math.round(s.today_rub || 0) + ' ₽, прогноз ' + Math.round(s.forecast_rub || 0) + ' ₽ в день') + '">' + grid + '<div class="chart__bars">' + bars + '</div></div>' +
      '<div class="chart__x">' + xs + '</div><div class="legend">' +
      '<span class="legend__item"><span class="legend__mark"></span><span class="legend__label">Прошедшие дни</span><span class="legend__value">' + t(s.legend_past || '') + '</span></span>' +
      '<span class="legend__item"><span class="legend__mark" style="background:var(--ink)"></span><span class="legend__label">Сегодня</span><span class="legend__value">' + Math.round(s.today_rub || 0) + ' ₽</span></span>' +
      '<span class="legend__item"><span class="legend__mark" style="background:var(--chart-empty)"></span><span class="legend__label">Прогноз</span><span class="legend__value">' + Math.round(s.forecast_rub || 0) + ' ₽ в день</span></span></div></div>';
  }

  function settingRow(key, title, meta, value, unit) {
    if (ui.edit === key) {
      return '<div class="row"><span class="row__main"><span class="row__meta">' + t(meta) + '</span><span class="setting__edit"><input class="input" data-edit="' + key + '" value="' + esc(value) + '" aria-label="' + esc(title) + '"' + (unit ? ' inputmode="numeric"' : '') + '>' + (unit ? '<span>' + unit + '</span>' : '') +
        '<button class="btn btn--primary" type="button" data-act="edit-save" data-key="' + key + '">Сохранить</button><button class="link" type="button" data-act="edit-cancel">Отмена</button></span></span></div>';
    }
    return '<div class="row"><span class="row__main"><span class="row__title">' + t(title) + '</span><span class="row__meta">' + t(meta) + '</span></span><button class="link row__action" type="button" data-act="edit" data-key="' + key + '">Изменить</button></div>';
  }
  function viewSettings() {
    var s = store.settings || {};
    var main = '<section class="panel">' + panelHead('Лимит на работу агента') +
      settingRow('limit_rub', money(s.limit_rub) + ' в месяц', 'Когда лимит потрачен, агент замолкает до 1-го числа, чат идёт менеджерам', s.limit_rub, '₽') +
      settingRow('warn_rub', 'Предупреждение при ' + money(s.warn_rub), 'Письмо получат менеджеры и бухгалтерия', s.warn_rub, '₽') +
      (s.server_rub ? '<p class="panel__note">' + t('Сервер ' + money(s.server_rub) + ' в месяц оплачивается отдельно и в лимит не входит') + '</p>' : '') + '</section>';
    main += '<section class="panel">' + panelHead('Что ещё делает агент') + '<div class="panel__list panel__list--tight">' + (s.functions || []).map(function (f) {
      return '<label class="row" style="cursor:pointer"><span class="row__main"><span class="row__title">' + t(f.title) + '</span><span class="row__meta">' + t(f.meta) + '</span></span><span class="switch"><input type="checkbox" data-act="fn" data-id="' + esc(f.id) + '"' + (f.on ? ' checked' : '') + ' aria-label="' + esc(f.title) + '"></span></label>';
    }).join('') + '</div><p class="panel__note">' + t('Выключенная функция не тратит лимит. Ответы в чате на сайте останавливает только пауза') + '</p></section>';
    var side = '<section class="panel">' + panelHead('Срок ответа и часы менеджеров') +
      settingRow('answer_min', 'Ответ клиенту за ' + s.answer_min + ' минут', 'Этот срок агент называет клиенту, когда передаёт вопрос менеджеру', s.answer_min, 'мин') +
      settingRow('hours', s.hours || '', 'В эти часы агент сразу передаёт сложный случай менеджеру', s.hours, '') +
      '<p class="panel__note">' + t('Вечером и в выходные агент пишет клиенту, что менеджер ответит до 10:00 следующего рабочего дня') + '</p></section>';
    side += '<section class="panel">' + panelHead('Модель') + '<div class="panel__list panel__list--tight" role="radiogroup" aria-label="Модель агента">' + (s.models || []).map(function (m) {
      return '<div class="model"><label class="radio"><input type="radio" name="model" value="' + esc(m.id) + '" data-act="model"' + (s.model === m.id ? ' checked' : '') + '>' + esc(m.name) + '</label><span class="model__price"><span class="model__cost">' + t(m.cost) + '</span><span class="t-muted">' + t(m.month) + '</span></span></div>';
    }).join('') + '</div>' + (s.model_note ? '<p class="panel__note">' + t(s.model_note) + '</p>' : '') + '</section>';
    return '<div class="columns"><div class="column">' + main + '</div><div class="column">' + side + '</div></div>';
  }
  function saveSettings(patch) {
    var s = store.settings;
    return act('settings', 'PUT', '/agent/settings', patch, function (res) { Object.assign(s, res && typeof res === 'object' && res.limit_rub != null ? res : patch); });
  }

  /* ---------- черновики полей переживают перерисовку ---------- */
  function restoreDrafts() {
    [].forEach.call(document.querySelectorAll('[data-draft]'), function (f) {
      var d = ui.drafts[f.getAttribute('data-id')]; if (!d) return;
      var k = f.getAttribute('data-draft');
      if (k === 'reason') f.checked = d.reason === f.value;
      else if (k === 'help') f.checked = !!d.help;
      else if (k === 'rule') { /* значение уже в разметке */ }
      else if (d[k] != null && f.value !== d[k]) f.value = d[k];
    });
  }
  document.addEventListener('input', function (e) {
    var f = e.target, k = f.getAttribute && f.getAttribute('data-draft');
    if (k) {
      var id = f.getAttribute('data-id'), d = ui.drafts[id] || (ui.drafts[id] = {});
      if (k === 'rule') { d.rule = d.rule || {}; d.rule[f.getAttribute('data-key')] = Number(f.value.replace(/\D/g, '')) || 0; return; }
      if (k === 'help') { d.help = f.checked; return; }
      if (k === 'reason') return;
      d[k] = f.value;
      var btn = f.closest('.case, .detail, .row, .detail__review');
      var b = btn && btn.querySelector('.btn--primary');
      if (b && (k === 'fix' || (k === 'reply' && findCase(id) && findCase(id).kind === 'answer') || (k === 'text' && id.indexOf('g-') === 0))) b.disabled = !f.value.trim();
      return;
    }
    var a = f.getAttribute && f.getAttribute('data-act');
    if (a === 'jsearch') { ui.jQuery = f.value; ui.jAll = false; rerenderKeep(f); }
    if (a === 'asearch') { ui.aQuery = f.value; rerenderKeep(f); }
  });
  // перерисовать и вернуть курсор в поле поиска
  function rerenderKeep(f) {
    var sel = '[data-act="' + f.getAttribute('data-act') + '"]', pos = f.selectionStart;
    render().then(function () { var n = $(sel); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} } });
  }
  document.addEventListener('change', function (e) {
    var f = e.target, k = f.getAttribute('data-draft'), a = f.getAttribute('data-act');
    if (k === 'reason') {
      var c = findCase(f.getAttribute('data-id')), d = draft(c);
      var prevAuto = replyFor(c, d.reason);
      d.reason = f.value;
      if (!d.reply || d.reply === prevAuto) d.reply = replyFor(c, d.reason);
      render().then(function () { if (f.value === 'Другая причина') { var ta = $('.case.is-open textarea'); if (ta) ta.focus(); } });
    }
    if (k === 'help') { var dh = ui.drafts[f.getAttribute('data-id')] || {}; dh.help = f.checked; ui.drafts[f.getAttribute('data-id')] = dh; }
    if (a === 'jscope') { if (f.getAttribute('data-key') === 'period') ui.jPeriod = f.value; else ui.jChannel = f.value; ui.jAll = false; render(); }
    if (a === 'fn') {
      var fn = byId(store.settings.functions, f.getAttribute('data-id')), on = f.checked;
      var list = store.settings.functions.map(function (x) { return x.id === fn.id ? Object.assign({}, x, { on: on }) : x; });
      saveSettings({ functions: list }).then(function () { toast(on ? 'Функция включена' : 'Функция выключена'); }, function () { f.checked = !on; });
    }
    if (a === 'model') saveSettings({ model: f.value }).then(function () { toast('Модель изменена'); render(); }, function () { render(); });
  });

  /* ---------- нажатия ---------- */
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.case.is-collapsed')) { e.preventDefault(); e.target.click(); }
    if (e.key === 'Enter' && e.target.matches && e.target.matches('[data-edit]')) { var b = $('[data-act="edit-save"]'); if (b) b.click(); }
    if (e.key === 'Escape' && ui.edit) { ui.edit = null; render(); }
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]'); if (!b || b.tagName === 'INPUT' || b.tagName === 'SELECT') return;
    var a = b.getAttribute('data-act'), id = b.getAttribute('data-id'), c = id ? findCase(id) : null;

    if (a === 'open') { ui.open = id; render(); return; }
    if (a === 'collapse') { ui.open = '__none'; render(); return; }
    if (a === 'history') {
      ui.history[id] = !ui.history[id];
      if (ui.history[id] && c && !c.events) {
        if (isLocal('cases')) c.events = [];
        else call('GET', '/cases/' + encodeURIComponent(id) + '/events').then(function (r) { c.events = r.events || []; render(); }, function () { c.events = []; render(); });
      }
      render(); return;
    }
    if (a === 'approve' && c) {
      decide(c, { action: 'approve' }, function () { c.status = 'approved'; c.decided_at = new Date().toISOString(); c.result = c.approve_result || 'Агент передал клиенту ваше согласие'; });
      return;
    }
    if (a === 'refuse' && c) { ui.refusing[id] = true; render(); return; }
    if (a === 'refuse-back') { delete ui.refusing[id]; render(); return; }
    if (a === 'refuse-send' && c) {
      var d = draft(c);
      if (!String(d.reply || '').trim()) { toast('Напишите, что агент ответит клиенту'); var ta = $('.case.is-open textarea'); if (ta) ta.focus(); return; }
      decide(c, { action: 'refuse', reason: d.reason, reply_text: d.reply }, function () {
        c.status = 'refused'; c.decided_at = new Date().toISOString();
        c.result = c.refuse_result || 'Агент ответил клиенту: ' + lcfirst(d.reply.length > 90 ? d.reply.slice(0, 88) + '…' : d.reply);
      });
      return;
    }
    if (a === 'answer' && c) {
      var da = draft(c);
      decide(c, { action: 'answer', reply_text: da.reply, add_to_help: !!da.help }, function () {
        c.status = 'answered'; c.decided_at = new Date().toISOString();
        c.result = da.help ? (c.answer_result_help || 'Агент передал клиенту ваш ответ и добавил его в справку') : (c.answer_result || 'Агент передал клиенту ваш ответ');
        if (da.help && store.knowledge && store.knowledge.articles) store.knowledge.articles.unshift({ id: 'a-' + c.id, title: c.title.replace(/^Вопрос без ответа в справке:\s*/, ''), meta: 'Вы добавили сегодня в ' + hm() + ' из ответа клиенту', text: da.reply });
      });
      return;
    }
    if (a === 'rule' && c) {
      var params = draft(c).rule || c.rule.params;
      act('cases', 'POST', '/rules', { case_id: c.id, params: params }, function () {
        if (store.knowledge && store.knowledge.rules) {
          var txt = c.rule.text.map(function (p) { var m = /^\{(\w+)\}$/.exec(p); return m ? Number(params[m[1]]).toLocaleString('ru-RU') : p; }).join(' ');
          store.knowledge.rules.unshift({ id: 'r-' + c.id, title: txt, meta: 'Такие просьбы агент согласует сам. Вы добавили правило сегодня в ' + hm() });
        }
      }).then(function () { ui.ruleDone[id] = true; toast('Правило добавлено, оно во вкладке «Знания»'); render(); }, function () {});
      return;
    }
    if (a === 'rule-later') { ui.ruleDone[id] = true; render(); return; }

    if (a === 'jfilter') { ui.jFilter = b.getAttribute('data-key'); ui.jAll = false; history.replaceState(null, '', '#journal'); render(); return; }
    if (a === 'jselect') { ui.jSel = id; render(); return; }
    if (a === 'jmore') { ui.jAll = true; render(); return; }
    if (a === 'jok' || a === 'jfix') {
      var fix = a === 'jfix' ? ((ui.drafts['j-' + id] || {}).fix || '').trim() : '';
      if (a === 'jfix' && !fix) return;
      act('journal', 'POST', '/journal/' + encodeURIComponent(id) + '/review', fix ? { fix: fix } : { ok: true }, function () {
        if (fix && store.knowledge && store.knowledge.fixes) {
          var it = byId(jItems(), id);
          store.knowledge.fixes.unshift({ id: 'f-' + id, title: fix, meta: 'Вы поправили сегодня в ' + hm() + (it && it.client ? ', разговор: ' + it.client : '') });
        }
      }).then(function () { reviewed(id); delete ui.drafts['j-' + id]; toast(fix ? 'Поправка сохранена, она во вкладке «Знания»' : 'Отметили: агент ответил верно'); render(); }, function () {});
      return;
    }

    var k = store.knowledge;
    if (a === 'k-add') {
      var p = byId(k.pending, id);
      act('knowledge', 'POST', '/knowledge/pending/' + encodeURIComponent(id) + '/add', null, function () {
        k.pending = without(k.pending, id);
        k.articles.unshift({ id: 'a-' + id, title: p.title, meta: 'Вы добавили сегодня в ' + hm() + ' из ответа менеджера', text: p.answer || '' });
      }).then(function () { toast('Ответ добавлен в справку'); render(); }, function () {});
      return;
    }
    if (a === 'k-rule') {
      var r = byId(k.rules, id), off = !r.off;
      act('knowledge', 'POST', '/rules/' + encodeURIComponent(id), { enabled: !off }, function () { r.off = off; }).then(function () { toast(off ? 'Правило выключено, такие просьбы снова идут вам' : 'Правило снова работает'); render(); }, function () {});
      return;
    }
    if (a === 'a-open') { ui.aOpen = ui.aOpen === id ? null : id; render(); return; }
    if (a === 'a-save') {
      var art = byId(k.articles, id), txt = (ui.drafts['a-' + id] || {}).text || '';
      act('knowledge', 'PUT', '/knowledge/articles/' + encodeURIComponent(id), { text: txt }, function () { art.text = txt; art.meta = 'Вы обновили сегодня в ' + hm(); }).then(function () { ui.aOpen = null; toast('Статья сохранена'); render(); }, function () {});
      return;
    }
    if (a === 'amore') { ui.aAll = true; render(); return; }
    if (a === 'g-open') { ui.gapOpen = ui.gapOpen === id ? null : id; render(); return; }
    if (a === 'g-save') {
      var g = byId(k.gaps, id), gt = ((ui.drafts['g-' + id] || {}).text || '').trim(); if (!gt) return;
      act('knowledge', 'POST', '/knowledge/articles', { title: g.title, text: gt }, function () {
        k.gaps = without(k.gaps, id); k.articles.unshift({ id: 'a-' + id, title: g.title, meta: 'Вы добавили сегодня в ' + hm(), text: gt });
      }).then(function () { ui.gapOpen = null; toast('Статья добавлена, агент будет отвечать по ней'); render(); }, function () {});
      return;
    }
    if (a === 'f-del') {
      act('knowledge', 'DELETE', '/knowledge/fixes/' + encodeURIComponent(id), null, function () { k.fixes = without(k.fixes, id); }).then(function () { toast('Поправка убрана'); render(); }, function () {});
      return;
    }

    if (a === 'pause') {
      var want = b.getAttribute('data-on') === '1';
      act('status', 'POST', '/agent/pause', { paused: want }, function (res) {
        store.status = res && res.state ? res : { state: want ? 'paused' : 'on', since: want ? new Date().toISOString() : null };
      }).then(function () { toast(want ? 'Агент на паузе, все чаты идут менеджерам' : 'Агент снова отвечает'); render(); }, function () {});
      return;
    }
    if (a === 'edit') { ui.edit = b.getAttribute('data-key'); render().then(function () { var f = $('[data-edit]'); if (f) { f.focus(); f.select(); } }); return; }
    if (a === 'edit-cancel') { ui.edit = null; render(); return; }
    if (a === 'edit-save') {
      var key = b.getAttribute('data-key'), f = $('[data-edit="' + key + '"]'), raw = f ? f.value.trim() : '';
      var val = key === 'hours' ? raw : Number(raw.replace(/[^\d]/g, ''));
      if (key !== 'hours' && !val) { toast('Введите число'); return; }
      if (key === 'warn_rub' && val >= store.settings.limit_rub) { toast('Предупреждение должно быть меньше лимита'); return; }
      var patch = {}; patch[key] = val;
      saveSettings(patch).then(function () { ui.edit = null; toast('Сохранено'); render(); }, function () {});
    }
  });

  /* ---------- обновление с сервера ---------- */
  // на «Сегодня» новые случаи приходят без перезагрузки; пока менеджер печатает, экран не трогаем
  var lastCases = '';
  function refresh() {
    if (DEMO) return;
    var busy = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    call('GET', '/agent/status').then(function (s) { store.status = s; store.sample.status = false; renderTop(); }, function () { store.sample.status = true; });
    if (ui.tab !== 'today' && ui.tab !== 'agent') return;
    call('GET', '/cases').then(function (d) {
      var sig = JSON.stringify(d); store.sample.cases = false;
      if (sig === lastCases) return; lastCases = sig;
      var events = {}; cases().forEach(function (c) { if (c.events) events[c.id] = c.events; });
      store.cases = d; cases().forEach(function (c) { if (!c.events && events[c.id]) c.events = events[c.id]; });
      if (ui.tab === 'today' && !busy) render(); else renderTop();
    }, function () {});
  }

  window.addEventListener('hashchange', route);
  if (DEMO) store.status = copy(SAMPLE.status);
  else call('GET', '/agent/status').then(function (s) { store.status = s; renderTop(); }, function () { store.status = { state: 'on' }; store.sample.status = true; });
  loadToday().then(function () { lastCases = DEMO ? '' : JSON.stringify(store.cases); route(); });
  setInterval(refresh, 5000);
})();
