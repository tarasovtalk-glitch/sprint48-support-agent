/* Кабинет менеджера по экранам Figma М1–М7: «Сегодня», «Журнал», «Знания», «Агент» (работа и настройки).
   Данные берёт с сервера агента через api.js (контракт в корневом README), без ключей в браузере.
   DEMO=1 при сборке: всё на примере данных из demo-data.js, действия меняют только эту страницу.
   В демо можно открыть состояния с макета: ?limit (лимит потрачен), ?paused (пауза), ?empty (очередь пуста).
   Если сервер не отдаёт раздел, вкладка сообщает, что данные недоступны.
   Все окна свои: меню, календарь, подсказки, подтверждения и уведомления. Системных alert и select нет. */
(function () {
  'use strict';
  var CFG = window.SUPPORT_CONFIG || {};
  var DEMO = !!CFG.demo;
  var API = String(CFG.apiBase || '/support/api').replace(/\/$/, '');
  var SAMPLE = window.CABINET_DEMO;
  var VARIANT = DEMO ? (/[?&](limit|paused|empty)\b/.exec(location.search) || [])[1] : null;

  /* ---------- мелочи ---------- */
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  var MONTHS_1 = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
  var WEEKDAYS = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }
  function copy(v) { return v == null ? v : JSON.parse(JSON.stringify(v)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  // неразрывные пробелы: короткое слово держится за следующее, ₽, % и единицы за число
  function ty(s) {
    s = String(s == null ? '' : s);
    for (var i = 0; i < 2; i++) s = s.replace(/(^|[\s(«])([а-яёa-z]{1,3}|[А-ЯЁ][а-яё]{0,2}|\d{1,3}|№|≈) (?=\S)/g, '$1$2\u00a0');
    return s.replace(/(\d) (?=\d{3}\b)/g, '$1\u00a0').replace(/(\d) (₽|%|мин\b|ч\b|с\b|шт\b)/g, '$1\u00a0$2').replace(/ (—|–)/g, '\u00a0$1');
  }
  function t(s) { return esc(ty(s)); }
  // **жирное** и перенос строки из текстов с макета
  function rich(s) { return t(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>'); }
  function group3(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0'); }
  function money(n) { return group3(Math.round(n)) + '\u00a0₽'; }
  function rub2(n) { var r = Math.round(n * 100) / 100, k = Math.floor(r); return group3(k) + ',' + ('0' + Math.round((r - k) * 100)).slice(-2) + '\u00a0₽'; }
  function dec(n, d) { return String((Math.round(n * Math.pow(10, d)) / Math.pow(10, d)).toFixed(d)).replace('.', ','); }
  function two(n) { return (n < 10 ? '0' : '') + n; }
  function hmOf(m) { return Math.floor(m / 60) + ':' + two(m % 60); }
  function mins(x) {
    if (x == null || x === '') return null;
    var m = /^(\d{1,2}):(\d{2})$/.exec(x);
    if (m) return +m[1] * 60 + +m[2];
    var d = new Date(x); return isNaN(d) ? null : d.getHours() * 60 + d.getMinutes();
  }
  function hm(x) { var m = mins(x); return m == null ? '' : hmOf(m); }
  function plural(n, one, few, many) { var a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many; }
  function dur(m) { return m < 60 ? m + '\u00a0мин' : Math.floor(m / 60) + '\u00a0ч' + (m % 60 ? ' ' + (m % 60) + '\u00a0мин' : ''); }
  function midnight(d) { var x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
  function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
  function num(v) { var n = Number(String(v).replace(/[^\d.,]/g, '').replace(',', '.')); return isFinite(n) ? n : NaN; }

  var IC = {
    chev: '<svg class="chev" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    search: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M14.2 9A5.2 5.2 0 1 1 3.8 9a5.2 5.2 0 0 1 10.4 0Z" stroke="#67646F" stroke-width="1.6"/><path d="M13 13L16.2 16.2" stroke="#67646F" stroke-width="1.6" stroke-linecap="round"/></svg>',
    check: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3.5 8.4L6.4 11.2L12.5 4.8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    prev: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M10 4L6 8L10 12" stroke="#393446" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    next: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M6 4L10 8L6 12" stroke="#393446" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  };
  var BOT = '<img class="avatar avatar--24 avatar--bot" src="avatar-bot.svg" width="24" height="24" alt="">';
  function badge(tone, text) { return '<span class="badge"><span class="dot dot--' + tone + '" aria-hidden="true"></span>' + t(text) + '</span>'; }
  function counter(n, grey) { return '<span class="counter' + (grey ? ' counter--grey' : '') + '">' + n + '</span>'; }
  function fact(label, value, dotTone) {
    return '<div class="fact"><span class="fact__label">' + t(label) + '</span><span class="fact__lead" aria-hidden="true"></span><span class="fact__value">' +
      (dotTone ? '<span class="badge">' + '<span class="dot dot--' + dotTone + '"></span>' + t(value) + '</span>' : t(value)) + '</span></div>';
  }
  function facts(list, plain) { return '<div class="facts' + (plain ? ' facts--plain' : '') + '">' + list.map(function (f) { return fact(f[0], f[1], f[2] === 'ok' ? 'success' : f[2] === 'fail' ? 'danger' : ''); }).join('') + '</div>'; }

  /* ---------- уведомление внизу слева ---------- */
  var toastTimer = 0;
  function toast(text) {
    var el = $('#toast');
    el.innerHTML = IC.check + '<span>' + t(text) + '</span>';
    el.classList.add('is-on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.classList.remove('is-on'); }, 4000);
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
  // Примеры доступны только в явно выбранном деморежиме.
  function load(key, path, sample) {
    if (DEMO) { if (store[key] == null) store[key] = copy(sample); return Promise.resolve(store[key]); }
    return call('GET', path).then(function (d) { store.sample[key] = false; store[key] = d; return d; }, function (e) {
      store.sample[key] = (e && e.status) || true; store[key] = null; return null;
    });
  }
  function isLocal(key) { return DEMO; }
  // действие: на сервер, а в примере только на странице
  function act(key, method, path, body, local) {
    if (isLocal(key)) { var r = local ? local() : null; return Promise.resolve(r); }
    return call(method, path, body).then(function (res) { if (local) local(res); return res; }, function (e) {
      toast(e && e.status === 409 ? 'Обращение уже изменилось, обновите страницу' : 'Не получилось сохранить: сервер агента не ответил'); throw e;
    });
  }
  // часы истории: в примере всегда 10:08, как на макете; с сервером настоящее время
  function storyNow(key) { return isLocal(key) ? SAMPLE.now : hmOf(mins(new Date().toISOString())); }

  /* ---------- состояние страницы ---------- */
  var ui = {
    tab: 'today', sub: 'work', sel: null, lastTab: null, lastSel: null,
    kpClosed: {}, kpEdit: {}, discount: {}, talkAll: {}, drafts: {}, help: {}, typing: {}, busy: {},
    jDay: midnight(new Date()), jFilter: null, jQuery: '', jOpen: {}, jSel: null,
    kQuery: '', kOpen: {}, kAll: false, benefit: null
  };

  function route() {
    var h = (location.hash || '#today').slice(1).split('/');
    ui.tab = ['today', 'journal', 'knowledge', 'agent'].indexOf(h[0]) >= 0 ? h[0] : 'today';
    if (ui.tab === 'agent') ui.sub = h[1] === 'settings' ? 'settings' : 'work';
    $$('.tab').forEach(function (a) {
      var on = a.getAttribute('data-tab') === ui.tab;
      a.classList.toggle('is-active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    closePop(true);
    return render();
  }

  var renderVersion = 0;
  function render() {
    var v = $('#view'), tab = ui.tab, version = ++renderVersion;
    function renderSection() {
      var ready = tab === 'today' ? loadToday()
        : tab === 'journal' ? Promise.all([loadToday(), load('journal', '/journal', SAMPLE.journal)])
        : tab === 'knowledge' ? load('knowledge', '/knowledge', SAMPLE.knowledge)
        : DEMO ? Promise.all([load('stats', '/agent/stats', SAMPLE.stats), load('settings', '/agent/settings', SAMPLE.settings)])
        : load('metrics', '/agent/metrics');
      return ready.then(function (data) {
        if (version !== renderVersion) return;
        var html = !data || (tab === 'journal' && !store.journal)
          ? '<p class="muted">Данные раздела пока недоступны.</p>'
          : tab === 'today' ? viewToday() : tab === 'journal' ? viewJournal()
          : tab === 'knowledge' ? (DEMO ? viewKnowledge() : viewAnswers(data))
          : DEMO ? viewAgent() : viewMetrics(data);
        var fresh = ui.lastTab !== tab + ui.sub;
        ui.lastTab = tab + ui.sub;
        v.innerHTML = '<div class="' + (fresh ? 'view-in' : '') + '">' + html + '</div>';
        renderTop(); restoreDrafts(); ensureTalk();
      });
    }
    if (DEMO || store.role) return renderSection();
    return call('GET', '/access').then(function (data) {
      if (version !== renderVersion) return;
      store.role = data.role;
      return renderSection();
    }, function () {
      if (version !== renderVersion) return;
      store = { sample: {} };
      ui.drafts = {};
      v.innerHTML = '';
      renderTop();
    });
  }

  function loadToday() { return load('cases', '/cases', SAMPLE.cases); }
  function cases() { return (store.cases && store.cases.cases) || []; }
  function findCase(id) { return cases().filter(function (c) { return c.id === id; })[0]; }
  // очередь: ждут решения и разговоры, где менеджер в чате; раньше всех просроченные и с ближним сроком
  function queue() {
    return cases().filter(function (c) { return c.status === 'waiting' || c.status === 'in-chat'; }).sort(function (a, b) {
      return (deadlineMin(a) == null ? 1e9 : deadlineMin(a)) - (deadlineMin(b) == null ? 1e9 : deadlineMin(b));
    });
  }
  function deadlineMin(c) {
    if (!c.deadline) return null;
    if (/^\d{1,2}:\d{2}$/.test(c.deadline)) return mins(c.deadline);
    return (Date.parse(c.deadline) - midnight(new Date()).getTime()) / 60000;
  }
  function lateMin(c) {
    var d = deadlineMin(c); if (d == null) return 0;
    var now = isLocal('cases') ? mins(SAMPLE.now) : (Date.now() - midnight(new Date()).getTime()) / 60000;
    return Math.floor(now - d);
  }
  function caseBadge(c) {
    if (c.status === 'in-chat') return badge('accent', 'Вы в чате с клиентом');
    if (c.status === 'done') return badge(c.done_tone || 'success', c.done_label || 'Готово');
    if (c.status === 'review') return badge('accent', 'Проверить ответ агента');
    if (c.status === 'active') return badge('neutral', c.done_label || 'Агент ведёт разговор');
    if (!c.deadline) return badge('neutral', 'Ждёт решения');
    var late = lateMin(c);
    return badge('danger', late > 0 ? 'Просрочено на ' + dur(late) : (c.deadline_label || 'Ответ до') + ' ' + hm(c.deadline));
  }
  function status() { return store.status || { state: 'on' }; }
  function silent() { var s = status().state; return s === 'limit' || s === 'paused' || s === 'down'; }

  /* ---------- шапка: счётчик, состояние агента, строка-предупреждение ---------- */
  function renderTop() {
    var n = queue().length, c = $('#todayCounter');
    c.hidden = !store.cases || ui.tab === 'today' || !n; c.textContent = n;
    var st = status().state, h;
    // состояние агента сервер пока не отдаёт: с живым API переключатель паузы не показываем, чтобы не обещать того, чего нет
    if (!DEMO) h = '';
    else if (st === 'limit') h = '<div class="status status--plain">' + badge('danger', 'Лимит потрачен') + '<button class="btn btn--accent" type="button" data-act="limit">Поднять лимит</button></div>';
    else if (st === 'down') h = '<div class="status status--plain">' + badge('danger', 'Агент не отвечает, чаты ведут менеджеры') + '</div>';
    else if (st === 'paused') h = '<div class="status status--paused"><span>Агент на паузе</span><button class="switch switch--agent" type="button" role="switch" aria-checked="false" aria-label="Включить агента" data-act="resume"></button></div>';
    else h = '<div class="status"><span>Агент работает</span><button class="switch switch--agent" type="button" role="switch" aria-checked="true" aria-label="Поставить агента на паузу" data-act="pause"></button></div>';
    $('#agentStatus').innerHTML = h;
    var note = store.role === 'jury' ? 'Доступ жюри · учебные обращения, только просмотр' : '';
    var el = $('#notice'); el.hidden = !note; el.innerHTML = note ? badge('danger', note) : '';
  }

  function viewMetrics(data) {
    return '<section class="panel"><h2 class="h2">' + (data.sample ? 'Статистика учебных диалогов' : 'Статистика стенда') + '</h2>' +
      facts([['Диалоги', data.cases], ['Вызовы модели', data.model_calls],
        ['Входящие токены', data.input_tokens], ['Исходящие токены', data.output_tokens],
        ['Расчётная стоимость', (data.cost_microrubles / 1000000).toLocaleString('ru-RU', { maximumFractionDigits: 4 }) + ' ₽']]) + '</section>';
  }

  function viewAnswers(data) {
    var answers = data.answers || [];
    return '<section class="panel"><h2 class="h2">Сохранённые ответы менеджеров</h2>' +
      (answers.length ? '<div class="glist">' + answers.map(function (entry) {
        return '<article class="plate"><b class="plate__title">' + t(entry.question) + '</b><p>' + rich(entry.answer) + '</p></article>';
      }).join('') + '</div>' : '<p class="nothing">Сохранённых ответов пока нет.</p>') + '</section>';
  }

  /* ---------- Сегодня ---------- */
  function viewToday() {
    var list = queue();
    if (!list.length) return viewEmpty();
    if (!ui.sel || !list.some(function (c) { return c.id === ui.sel; })) {
      var mine = list.filter(function (c) { return !c.owner; });
      ui.sel = (mine[0] || list[0]).id;
    }
    var c = findCase(ui.sel), swap = ui.lastSel !== ui.sel; ui.lastSel = ui.sel;
    var st = status();
    var head = '<section class="panel" aria-label="Ждут решения"><div class="panel__head"><h2 class="h2">Ждут решения</h2>' + counter(list.length) + '</div>' +
      (st.state === 'limit' || st.state === 'paused' ? '<p class="panel__note">' + t((st.since ? 'С ' + st.since + ' ' : 'Сейчас ') + 'агент молчит: новые чаты приходят сюда без его сводки.') + '</p>' : '') +
      '<div class="queue">' + list.map(queueRow).join('') + '</div></section>';
    return '<div class="today">' + head + '<div class="' + (swap ? 'swap-in' : '') + '" style="min-width:0">' + caseCard(c, 'today') + '</div><div class="side' + (swap ? ' swap-in' : '') + '">' + talkPanel(c, true) + '</div></div>';
  }
  function avatar(c, size) {
    var a = '<span class="avatar' + (size === 24 ? ' avatar--24' : '') + '" aria-hidden="true">' + esc(c.initials || 'К') + '</span>';
    if (!c.owner) return a;
    return '<span class="avatar-wrap" aria-hidden="true">' + a + '<span class="avatar avatar--mini">' + esc(c.owner.initials) + '</span></span>';
  }
  function queueRow(c) {
    var f = (c.facts || [['Клиент', c.client]]);
    return '<button class="qrow' + (c.id === ui.sel ? ' is-selected' : '') + '" type="button" data-act="pick" data-id="' + esc(c.id) + '" aria-pressed="' + (c.id === ui.sel) + '">' +
      '<span class="qrow__top"><span class="qrow__title">' + t(c.queue_title || c.title) + '</span>' + avatar(c) + '</span>' + caseBadge(c) +
      '<span class="facts">' + f.map(function (x) { return fact(x[0], x[1]); }).join('').replace(/<div/g, '<span').replace(/<\/div>/g, '</span>') + '</span></button>';
  }
  function viewEmpty() {
    var s = store.settings || {}, rec = (store.cases && store.cases.recent) || [];
    var how = !(DEMO || !store.sample.settings) ? '' : s.notify !== false && s.channel === 'telegram' ? ', а в Telegram придёт уведомление' : s.notify !== false && s.channel === 'max' ? ', а в MAX придёт уведомление' : '';
    return '<div class="empty"><div class="empty__head"><p class="empty__title">Решений сейчас нет,<span>агент отвечает клиентам сам</span></p>' +
      '<p class="empty__sub">' + t('Когда агент передаст разговор, он появится здесь' + how + '.') + '</p><a class="btn btn--grey" href="#journal">Открыть журнал</a></div>' +
      (rec.length ? '<section class="panel"><h2 class="h2">Последние разговоры агента</h2><div class="glist">' + rec.map(function (r) {
        return '<div class="lrow" style="margin:0;width:100%;padding:8px 0"><span class="lrow__line"><span class="lrow__title">' + t(r.title) + '</span><span class="lrow__time">' + esc(r.time) + '</span></span>' +
          '<span class="lrow__line"><span class="lrow__status"><span class="dot dot--success"></span>' + t(r.status) + '</span><span class="lrow__client">' + t(r.client) + '</span></span></div>';
      }).join('') + '</div></section>' : '') + '</div>';
  }

  /* карточка случая: та же в «Сегодня» и в «Журнале» */
  function caseCard(c, mode) {
    if (!c) return '<section class="case"><p class="muted">Выберите разговор слева</p></section>';
    var id = esc(c.id), inChat = c.status === 'in-chat', price = kpTotal(c);
    var h = '<section class="case" aria-label="' + esc(c.title) + '"><div class="case__top' + (price == null || inChat ? ' case__top--short' : '') + '">' + caseBadge(c) +
      (price != null && !inChat ? '<span class="num" id="price-' + id + '">' + money(price) + '</span>' : '') + '</div>';
    h += '<div class="case__intro"><div class="case__about"><h2 class="h2">' + t(c.title) + '</h2>' +
      (c.first ? '<p class="bubble" title="' + esc(c.first) + '"><span>' + t(c.first) + '</span></p>' : '') +
      (c.summary ? '<p class="effect">' + t(c.summary) + '</p>' : '') +
      (c.reason_text ? '<p class="muted">' + t(c.reason_text) + '</p>' : '') + '</div>' + stepsHtml(c) + '</div>';

    if (store.role === 'jury') return h + (c.kp ? '<hr class="dash">' + kpHtml(c, false) : '') + '</section>';

    if (mode === 'journal' && (c.status === 'waiting' || c.status === 'in-chat')) {
      h += '<p class="effect">' + rich(c.owner ? c.effect : 'Решение ждёт во вкладке «Сегодня»: там ответ клиенту и все действия.') + '</p>' +
        (c.owner ? '' : '<div class="case__buttons"><button class="btn btn--grey" type="button" data-act="goto-today" data-id="' + id + '">Открыть в «Сегодня»</button></div>');
      return h + '</section>';
    }
    if (c.owner) return h + '<p class="effect">' + rich(c.effect) + '</p></section>';

    if (c.kind === 'quote' && c.status === 'waiting') {
      var edit = ui.kpEdit[c.id], open = !ui.kpClosed[c.id] || edit;
      var canEdit = isLocal('cases') || c.can_discount;
      h += '<p class="effect">' + rich(edit ? 'Поменять можно только скидку. **Итог и НДС пересчитаются**, клиент получит уже исправленное КП.' : silent() && c.effect_silent ? c.effect_silent : c.effect) + '</p>';
      h += '<div class="case__actions"><div class="case__buttons"><button class="btn btn--accent' + (ui.busy[c.id] ? ' is-busy' : '') + '" type="button" data-act="send-kp" data-id="' + id + '">' + (ui.busy[c.id] ? 'Отправляю…' : 'Отправить КП в чат') + '</button>' +
        (canEdit ? (edit ? '<button class="btn btn--grey" type="button" data-act="cancel-edit" data-id="' + id + '">Отменить правку</button>' : '<button class="btn btn--grey" type="button" data-act="edit-kp" data-id="' + id + '">Поправить</button>') : '') + '</div>' +
        (edit || !c.kp ? '' : collapseBtn(c, open)) + '</div>';
      if (open && c.kp) h += '<hr class="dash">' + kpHtml(c, edit);
      return h + '</section>';
    }
    if (c.kind !== 'quote' && c.status === 'waiting') {
      var d = draft(c);
      h += '<hr class="dash"><div class="reply"><label class="label"><span class="label__text medium">Ответ для клиента</span>' +
        '<textarea class="field" rows="2" data-draft="reply" data-id="' + id + '" placeholder="Что ответить клиенту">' + esc(d.reply) + '</textarea></label>' +
        (c.help_option ? '<label class="check"><button class="switch" type="button" role="switch" aria-checked="' + (DEMO ? d.help !== false : d.help === true) + '" data-act="help" data-id="' + id + '" aria-label="Добавить ответ в справку"></button>' + t('Добавить ответ в справку, в следующий раз агент ответит сам') + '</label>' : '') + '</div>';
      h += '<p class="effect">' + rich(c.effect) + '</p><div class="case__buttons"><button class="btn btn--accent' + (ui.busy[c.id] ? ' is-busy' : '') + '" type="button" data-act="answer" data-id="' + id + '" data-needs="reply"' + (String(d.reply || '').trim() ? '' : ' disabled') + '>' + (ui.busy[c.id] ? 'Отправляю…' : 'Ответить клиенту') + '</button></div>';
      return h + '</section>';
    }
    if (inChat) {
      return h + '<hr class="dash"><p class="effect">' + rich(c.in_chat && c.in_chat.effect || 'Агент молчит, пока вы в чате. **Верните ему разговор**, когда вопрос решён.') + '</p>' +
        '<div class="case__buttons"><button class="btn btn--accent" type="button" data-act="return" data-id="' + id + '">Вернуть агенту</button></div></section>';
    }
    if (c.status === 'review') {
      var r = ui.drafts['fix-' + c.id] || (ui.drafts['fix-' + c.id] = { fix: '' });
      return h + '<p class="effect">' + rich(c.effect) + '</p><hr class="dash"><div class="reply"><label class="label"><span class="label__text medium">Как надо было ответить</span>' +
        '<textarea class="field" rows="2" data-draft="fix" data-id="fix-' + id + '" placeholder="Например: редакцию из запроса клиента не менять">' + esc(r.fix) + '</textarea></label></div>' +
        '<div class="case__buttons"><button class="btn btn--accent" type="button" data-act="jfix" data-id="' + id + '" data-needs="fix"' + (r.fix.trim() ? '' : ' disabled') + '>Сохранить поправку</button>' +
        '<button class="btn btn--grey" type="button" data-act="jok" data-id="' + id + '">Агент ответил верно</button></div></section>';
    }
    // закрытый разговор
    var kpOpen = c.kp && !ui.kpClosed[c.id];
    h += '<div class="case__actions"><p class="effect">' + rich(c.effect || '') + '</p>' + (c.kp ? collapseBtn(c, kpOpen) : '') + '</div>';
    if (kpOpen) h += '<hr class="dash">' + kpHtml(c, false);
    return h + '</section>';
  }
  function collapseBtn(c, open) {
    return '<button class="pill' + (open ? ' is-up' : '') + '" type="button" data-act="kp-toggle" data-id="' + esc(c.id) + '" aria-expanded="' + open + '">' + (open ? 'Свернуть КП' : 'Показать КП') + IC.chev + '</button>';
  }
  function stepsHtml(c) {
    if (c.steps == null) return isLocal('cases') ? '' : '<div class="path"><p class="medium">Что сделал агент</p><p class="muted">Загружаю шаги…</p></div>';
    if (!c.steps.length) return '';
    var title = c.status === 'in-chat' ? 'Что сделано' : 'Что сделал агент';
    return '<div class="path"><p class="medium">' + title + '</p><ol class="path__list" style="margin:0;padding:0;list-style:none">' + c.steps.map(function (s) {
      return '<li class="step"><span class="step__time">' + esc(s[0]) + '</span><span class="step__node" aria-hidden="true"></span><span>' + t(s[1]) + '</span></li>';
    }).join('') + '</ol></div>';
  }
  function draft(c) {
    var d = ui.drafts[c.id] || (ui.drafts[c.id] = {});
    if (d.reply == null) d.reply = c.reply_draft || '';
    return d;
  }

  /* КП: позиции, скидка, итог и НДС считаются из позиций, чтобы цифры не расходились */
  function kpSum(c) { return (c.kp && c.kp.items || []).reduce(function (s, i) { return s + (i.qty || 1) * i.price; }, 0); }
  function kpDiscount(c) { return ui.kpEdit[c.id] ? (ui.discount[c.id] || 0) : (c.kp && c.kp.discount) || 0; }
  function kpTotal(c) {
    if (!c.kp) return c.amount_rub != null ? c.amount_rub : null;
    return Math.round(kpSum(c) * (1 - kpDiscount(c) / 100) * 100) / 100;
  }
  function kpHtml(c, edit) {
    var k = c.kp, total = kpTotal(c), vat = k.vat_rate === 0 ? null : (k.vat_rate || 22);
    var h = '<div class="kp-wrap"><div class="kp"><div class="kp__head"><p class="medium">' + t('Коммерческое предложение' + (k.number ? ' № ' + k.number : '')) + '</p>' +
      '<p class="muted">' + t('ПАО «Софтлайн» для ' + k.buyer) + '</p></div>';
    h += k.items.map(function (i) {
      return '<div class="kp__item"><div class="kp__row"><span class="medium">' + t(i.name) + '</span><span class="fact__lead" aria-hidden="true"></span><span>' + t((i.qty || 1) + ' × ' + rub2(i.price)) + '</span></div>' +
        (i.note ? '<p class="muted">' + t(i.note) + '</p>' : '') + '</div>';
    }).join('');
    if (edit) {
      h += '<div class="kp__discount"><label class="muted" for="disc-' + esc(c.id) + '" style="flex:1">Скидка</label><input class="field field--num" id="disc-' + esc(c.id) + '" inputmode="decimal" autocomplete="off" data-act="discount" data-id="' + esc(c.id) + '" value="' + esc(String(ui.discount[c.id] || 0).replace('.', ',')) + '"><span class="muted">%</span></div>';
    } else if (kpDiscount(c)) {
      h += '<div class="kp__row"><span class="muted">Скидка</span><span class="fact__lead"></span><span>' + t(String(kpDiscount(c)).replace('.', ',') + '%') + '</span></div>';
    }
    h += '<div class="kp__total"><div class="kp__row"><span>Итого</span><span class="fact__lead" aria-hidden="true"></span><span class="fact__value" data-kp="total">' + t(rub2(total)) + '</span></div>' +
      (vat ? '<div class="kp__row muted"><span>' + t('в т. ч. НДС ' + vat + '%') + '</span><span class="fact__lead" aria-hidden="true"></span><span data-kp="vat">' + t(rub2(total * vat / (100 + vat))) + '</span></div>' : '') + '</div>';
    if (k.terms && k.terms.length) h += '<div class="kp__terms">' + k.terms.map(function (x) { return fact(x[0], x[1]); }).join('') + '</div>';
    return h + '</div></div>';
  }

  /* разговор в чате: последние реплики, раньше под «Ещё N»; в чате с клиентом поле ответа */
  function talkPanel(c, withComposer) {
    if (!c) return '';
    var earlier = c.talk_earlier || [], all = ui.talkAll[c.id];
    var lines = c.talk == null ? null : (all ? earlier.concat(c.talk) : c.talk);
    var h = '<section class="talk" aria-label="Разговор в чате"><div class="talk__head"><span>Разговор в чате</span>' +
      (earlier.length ? '<button class="pill pill--small' + (all ? '' : ' is-up') + '" type="button" data-act="more" data-id="' + esc(c.id) + '" aria-expanded="' + !!all + '">' + (all ? 'Свернуть' : 'Ещё ' + earlier.length) + IC.chev + '</button>' : '') + '</div>';
    h += '<div class="talk__body" id="talk-' + esc(c.id) + '">' + (lines == null ? '<p class="muted">Загружаю переписку…</p>' : lines.map(lineHtml).join('')) +
      (ui.typing[c.id] ? '<div class="line line--typing is-new"><span class="avatar avatar--24" aria-hidden="true">' + esc(c.initials || 'К') + '</span><p>Клиент печатает<span class="typing" aria-hidden="true"><i></i><i></i><i></i></span></p></div>' : '') + '</div>';
    if (withComposer && c.status === 'in-chat') {
      var d = ui.drafts['say-' + c.id] || (ui.drafts['say-' + c.id] = { say: '' });
      h += '<div class="composer"><textarea class="field" rows="2" data-draft="say" data-id="say-' + esc(c.id) + '" placeholder="Ответ клиенту" aria-label="Ответ клиенту">' + esc(d.say) + '</textarea>' +
        '<button class="btn btn--accent" type="button" data-act="say" data-id="' + esc(c.id) + '" data-needs="say"' + (d.say.trim() ? '' : ' disabled') + '>Отправить</button></div>';
    }
    return h + '</section>';
  }
  function lineHtml(l) {
    var av = l.who === 'agent' ? BOT : l.who === 'client' ? '<span class="avatar avatar--24" aria-hidden="true">К</span>'
      : '<span class="avatar avatar--24 avatar--staff" aria-hidden="true">' + esc(l.who === 'me' ? 'А' : l.initials || (l.name || 'М').charAt(0)) + '</span>';
    var who = l.who === 'agent' ? 'Агент' : l.who === 'client' ? 'Клиент' : l.who === 'me' ? 'Антон' : l.name || 'Менеджер';
    return '<div class="line' + (l._new ? ' is-new' : '') + '">' + av + '<p><span class="line__who">' + esc(who) + '</span> ' + t(l.text) + '</p></div>';
  }
  // переписка и шаги с сервера приходят отдельным запросом, когда карточку открыли
  function ensureTalk() {
    if (isLocal('cases') && (ui.tab === 'today' || !jItemLive())) return;
    var c = ui.tab === 'today' ? findCase(ui.sel) : ui.tab === 'journal' ? jDetail(jSelected()) : null;
    if (!c || c.talk != null || c._loading || !c.id) return;
    c._loading = true;
    call('GET', '/cases/' + encodeURIComponent(c.id) + '/events').then(function (r) {
      c._loading = false;
      var all = r.talk || [];
      c.talk_earlier = all.length > 4 ? all.slice(0, all.length - 4) : [];
      c.talk = all.length > 4 ? all.slice(-4) : all;
      if (c.steps == null) c.steps = r.steps || [];
      if (r.cost && !c.cost) c.cost = r.cost;
      if (!c.first) { var cl = all.filter(function (l) { return l.who === 'client'; }); if (cl.length) c.first = cl[cl.length - 1].text; }
      render();
    }, function () { c._loading = false; c.talk = []; if (c.steps == null) c.steps = []; render(); });
  }
  function jItemLive() { return !isLocal('journal'); }

  /* ---------- Журнал ---------- */
  function jItemsFor(day) {
    var all = (store.journal && store.journal.items) || [], today = midnight(new Date());
    if (!isLocal('journal')) return all.filter(function (it) { return it.time && sameDay(new Date(it.time), day); });
    if (sameDay(day, today)) return all;
    // прошлые дни в примере: те же темы, все разговоры закрыты
    var back = Math.round((today - day) / 864e5), keep = 30 + (back * 7) % 17;
    return all.filter(function (it) { return !it.case_id && !it.review && it.id !== 'vector'; }).slice(0, keep).map(function (it) {
      var x = copy(it); x.id = it.id + '-' + back; x.status = { tone: 'success', text: it.status.text }; return x;
    });
  }
  function jStatus(it) {
    if (!it.case_id) return it.status || { tone: 'neutral', text: '' };
    var c = findCase(it.case_id);
    if (!c) return it.status;
    if (c.owner && c.status === 'waiting') return { tone: 'neutral', text: 'Отвечает ' + c.owner.name, open: true };
    if (c.status === 'waiting') return { tone: 'neutral', text: 'Ждёт ответа', open: true };
    if (c.status === 'in-chat') return { tone: 'accent', text: 'Вы в чате', open: true };
    return { tone: 'success', text: (c.done_label || 'Готово').replace(/ в \d{1,2}:\d{2}$/, '') };
  }
  function jDetail(it) { if (!it) return null; return it.case_id ? findCase(it.case_id) || it.detail : it.detail; }
  function jSelected() { return jItemsFor(ui.jDay).filter(function (i) { return i.id === ui.jSel; })[0]; }
  function dayLabel(d) {
    var today = midnight(new Date()), back = Math.round((today - midnight(d)) / 864e5);
    return back === 0 ? 'Сегодня' : back === 1 ? 'Вчера' : d.getDate() + ' ' + MONTHS[d.getMonth()];
  }
  function jGroups(items, day) {
    var s = store.settings || {}, start = mins(s.from || '9:00'), end = mins(s.to || '18:00'), defs = [];
    var isToday = sameDay(day, new Date()), now = isLocal('journal') ? mins(SAMPLE.now) : mins(new Date().toISOString());
    if (isToday && now >= start) {
      var h = Math.floor(now / 60) * 60;
      defs.push({ id: 'cur', label: 'С ' + hmOf(h), from: h, to: 1440 });
      if (h - 60 >= start) defs.push({ id: 'prev', label: hmOf(h - 60) + '–' + hmOf(h), from: h - 60, to: h });
      if (h - 60 > start) defs.push({ id: 'work', label: hmOf(start) + '–' + hmOf(h - 60), from: start, to: h - 60 });
    } else if (!isToday) {
      defs.push({ id: 'eve', label: 'После ' + hmOf(end), from: end, to: 1440 }, { id: 'work', label: hmOf(start) + '–' + hmOf(end), from: start, to: end });
    }
    defs.push({ id: 'night', label: 'До ' + hmOf(start) + ', без менеджеров', from: 0, to: isToday && now < start ? 1440 : start });
    defs.forEach(function (g) { g.items = items.filter(function (it) { var m = mins(it.time); return m >= g.from && m < g.to; }); });
    return defs.filter(function (g) { return g.items.length; });
  }
  function viewJournal() {
    var day = ui.jDay, items = jItemsFor(day);
    var open = items.filter(function (i) { return jStatus(i).open; }).length, review = items.filter(function (i) { return i.review; }).length;
    var q = ui.jQuery.trim().toLowerCase();
    var shown = items.filter(function (it) {
      if (ui.jFilter === 'open' && !jStatus(it).open) return false;
      if (ui.jFilter === 'review' && !it.review) return false;
      return !q || (it.title + ' ' + it.client + ' ' + (it.inn || '') + ' ' + (it.order || '')).toLowerCase().indexOf(q) >= 0;
    });
    if (!ui.jSel || !shown.some(function (i) { return i.id === ui.jSel; })) {
      var pref = store.journal && store.journal.selected;
      ui.jSel = shown.some(function (i) { return i.id === pref; }) && sameDay(day, new Date()) ? pref : shown.length ? shown[0].id : null;
    }
    var groups = jGroups(shown, day), dk = day.toDateString(), filtered = !!(q || ui.jFilter);
    var left = '<section class="panel" aria-label="Разговоры"><div class="panel__head panel__head--between"><h2 class="h2">Разговоры</h2>' +
      (DEMO || store.role === 'jury' ? '' : '<button class="btn btn--grey" type="button" data-act="export-csv">CSV</button>') +
      '<button class="select" type="button" data-act="jday" aria-haspopup="menu" aria-expanded="false">' + esc(dayLabel(day)) + IC.chev + '</button></div>' +
      '<div class="chips"><button class="chip' + (ui.jFilter === 'open' ? ' is-active' : '') + '" type="button" data-act="jfilter" data-key="open" aria-pressed="' + (ui.jFilter === 'open') + '">Не закрыты' + counter(open, true) + '</button>' +
      '<button class="chip' + (ui.jFilter === 'review' ? ' is-active' : '') + '" type="button" data-act="jfilter" data-key="review" aria-pressed="' + (ui.jFilter === 'review') + '">Проверить' + counter(review, !review) + '</button></div>' +
      '<label class="search">' + IC.search + '<input class="field" type="search" data-act="jsearch" placeholder="Клиент, ИНН или № заказа" aria-label="Поиск по журналу" value="' + esc(ui.jQuery) + '"></label>' +
      '<div class="groups">' + (groups.length ? groups.map(function (g, i) {
        var key = dk + g.id, isOpen = filtered || (ui.jOpen[key] != null ? ui.jOpen[key] : i === 0);
        return '<div class="group"><button class="ghead" type="button" data-act="jgroup" data-key="' + esc(key) + '" data-open="' + isOpen + '" aria-expanded="' + isOpen + '"><span>' + t(g.label) + '</span>' + counter(g.items.length, true) + IC.chev + '</button>' +
          (isOpen ? '<div class="glist">' + g.items.map(jRow).join('') + '</div>' : '') + '</div>';
      }).join('') : '<p class="nothing">' + t(q ? 'Ничего не нашлось. Попробуйте название компании, ИНН или номер заказа' : ui.jFilter === 'review' ? 'Проверять нечего' : ui.jFilter === 'open' ? 'Незакрытых разговоров нет' : 'Разговоров за этот день нет') + '</p>') + '</div></section>';
    var it = jSelected(), c = jDetail(it), swap = ui.lastSel !== 'j' + ui.jSel; ui.lastSel = 'j' + ui.jSel;
    var side = c ? talkPanel(c, false) + (c.cost ? '<section class="card cost"><p class="medium">Во что обошёлся</p>' + facts(c.cost) + '</section>' : '') : '';
    return '<div class="today">' + left + '<div class="' + (swap ? 'swap-in' : '') + '" style="min-width:0">' + (c ? caseCard(c, 'journal') : '<section class="case"><p class="muted">Выберите разговор слева</p></section>') + '</div>' +
      '<div class="side' + (swap ? ' swap-in' : '') + '">' + side + '</div></div>';
  }
  function jRow(it) {
    var s = jStatus(it), sel = it.id === ui.jSel;
    return '<button class="lrow' + (sel ? ' is-selected' : '') + '" type="button" data-act="jpick" data-id="' + esc(it.id) + '" aria-pressed="' + sel + '">' +
      '<span class="lrow__line"><span class="lrow__title" title="' + esc(it.title) + '">' + t(it.title) + '</span><span class="lrow__time">' + esc(hm(it.time)) + '</span></span>' +
      '<span class="lrow__line"><span class="lrow__status' + (s.open ? ' is-open' : '') + '"><span class="dot dot--' + (s.tone || 'neutral') + '" aria-hidden="true"></span>' + t(s.text) + '</span><span class="lrow__client" title="' + esc(it.client) + '">' + t(it.client) + '</span></span></button>';
  }

  /* ---------- Знания ---------- */
  function kGroup(key, label, count, body, startOpen) {
    var open = ui.kQuery.trim() ? true : ui.kOpen[key] != null ? ui.kOpen[key] : startOpen !== false;
    return '<div class="group"><button class="ghead ghead--muted" type="button" data-act="kgroup" data-key="' + key + '" data-open="' + open + '" aria-expanded="' + open + '"><span>' + t(label) + '</span>' + counter(count, true) + IC.chev + '</button>' +
      (open ? '<div class="plates glist">' + body + '</div>' : '') + '</div>';
  }
  function plate(act, it, right) {
    return '<button class="plate" type="button" data-act="' + act + '" data-id="' + esc(it.id) + '"><span class="plate__line"><span class="plate__title">' + t(it.title) + '</span>' + (right ? '<span class="medium">' + t(right) + '</span>' : '') + '</span>' +
      (it.meta ? '<span class="plate__meta">' + t(it.meta) + '</span>' : '') + '</button>';
  }
  function viewKnowledge() {
    var k = store.knowledge || {}, q = ui.kQuery.trim().toLowerCase();
    var pending = k.pending || [], gaps = k.gaps || [], fixes = k.fixes || [];
    var match = function (x) { return !q || (x.title + ' ' + (x.meta || '') + ' ' + (x.text || '')).toLowerCase().indexOf(q) >= 0; };
    var rules = (k.rules || []).filter(match), arts = (k.articles || []).filter(match);
    var shownArts = ui.kAll || q ? arts : arts.slice(0, 5);
    var left = '<section class="panel" aria-label="Ждёт менеджера"><h2 class="h2">Ждёт менеджера</h2>' +
      (pending.length + gaps.length + fixes.length ? '<div class="groups">' +
        (pending.length ? kGroup('pending', 'Ответы для справки', pending.length, pending.map(function (p) { return plate('kpending', p); }).join('')) : '') +
        (gaps.length ? kGroup('gaps', 'Темы без ответа', gaps.length, gaps.map(function (g) { return plate('kgap', g, g.share); }).join('')) : '') +
        (fixes.length ? kGroup('fixes', 'Поправки из проверок', fixes.length, fixes.map(function (f) { return plate('kfix', f); }).join('')) : '') + '</div>'
        : '<p class="nothing">' + t('Всё разобрано: новых ответов, тем и поправок нет') + '</p>') + '</section>';
    var right = '<section class="panel" aria-label="Что знает агент"><h2 class="h2">Что знает агент</h2>' +
      '<label class="search">' + IC.search + '<input class="field" type="search" data-act="ksearch" placeholder="Правило, статья или слово" aria-label="Поиск по знаниям агента" value="' + esc(ui.kQuery) + '"></label><div class="groups">' +
      kGroup('rules', 'Правила агента', rules.length, rules.length ? rules.map(function (r) { return plate('krule', r); }).join('') : '<p class="nothing">Правил не нашлось</p>') +
      kGroup('arts', 'Статьи справки', q ? arts.length : (k.articles || []).length, shownArts.length ? shownArts.map(function (a) { return plate('karticle', a); }).join('') : '<p class="nothing">Статей не нашлось</p>') +
      '</div>' + (!q && !ui.kAll && arts.length > 5 && ui.kOpen.arts !== false ? '<div><button class="btn btn--grey" type="button" data-act="kall">Все статьи</button></div>' : '') + '</section>';
    return '<div class="knowledge">' + left + right + '</div>';
  }
  function byId(list, id) { return (list || []).filter(function (x) { return x.id === id; })[0]; }
  function without(list, id) { return (list || []).filter(function (x) { return x.id !== id; }); }

  /* ---------- Агент ---------- */
  function viewAgent() {
    return '<div class="agent"><nav class="subtabs" aria-label="Агент"><a class="subtab' + (ui.sub === 'work' ? ' is-active' : '') + '" href="#agent"' + (ui.sub === 'work' ? ' aria-current="page"' : '') + '>Работа</a>' +
      '<a class="subtab' + (ui.sub === 'settings' ? ' is-active' : '') + '" href="#agent/settings"' + (ui.sub === 'settings' ? ' aria-current="page"' : '') + '>Настройки</a></nav>' +
      (ui.sub === 'settings' ? viewSettings() : viewWork()) + '</div>';
  }
  function spend() {
    var s = store.stats || {}, past = (s.days || []).reduce(function (a, b) { return a + b; }, 0);
    var spent = status().state === 'limit' ? (store.settings || {}).limit_rub || 0 : Math.round(past + (s.today_rub || 0));
    var forecast = Math.round(past + (s.today_rub || 0) + (s.forecast_rub || 0) * ((s.days_in_month || 30) - (s.today_day || 1)));
    return { spent: spent, forecast: forecast };
  }
  function benefit() {
    var s = store.stats || {}, b = ui.benefit || (ui.benefit = copy(s.benefit || { minutes: 30, rate: 870 }));
    var closed = (s.requests || {}).closed || 0, hours = closed * (b.minutes || 0) / 60, gross = hours * (b.rate || 0);
    var cost = spend().spent + (s.server_rub || 0);
    return { hours: hours, gross: gross, cost: cost, net: gross - cost, per: cost ? gross / cost : 0 };
  }
  function viewWork() {
    var s = store.stats || {}, set = store.settings || {}, r = s.requests || {}, sp = spend(), limit = set.limit_rub || 0, warn = set.warn_rub || 0;
    var pct = function (n) { return r.total ? Math.round(n / r.total * 100) : 0; };
    var left = '<section class="panel"><h2 class="h2">Обращения ' + esc(s.month_in || '') + '</h2>' +
      '<div class="total"><span class="num">' + group3(r.total || 0) + '</span><span class="muted">' + t('обращений, сегодня ' + (r.today || 0)) + '</span></div>' +
      '<div class="split" role="img" aria-label="' + esc('Закрыл сам ' + pct(r.closed) + '%, передал менеджерам ' + pct(r.handed) + '%, не закончили ' + pct(r.unfinished) + '%') + '">' +
      '<span style="flex:' + r.closed + ';background:var(--success)"></span><span style="flex:' + r.handed + ';background:var(--accent);animation-delay:60ms"></span><span style="flex:' + r.unfinished + ';background:var(--icon);animation-delay:120ms"></span></div>' +
      '<div class="split__legend">' + [['success', 'Закрыл сам', r.closed], ['accent', 'Передал менеджерам', r.handed], ['neutral', 'Не закончили', r.unfinished]].map(function (x) {
        return '<div class="split__item">' + badge(x[0], x[1]) + '<span><b>' + pct(x[2]) + '%</b> <span class="muted">' + group3(x[2]) + '</span></span></div>';
      }).join('') + '</div>' + facts(s.speed || []) + '<p class="panel__note">' + t(s.speed_note || '') + '</p></section>';
    left += '<section class="panel"><h2 class="h2">Расходы на агента, ' + esc(s.month || '') + '</h2>' +
      '<div class="spend-head"><span class="total"><span class="num">' + money(sp.spent) + '</span><span class="muted">' + t('из лимита ' + money(limit)) + '</span></span>' +
      '<span class="muted">' + t('к ' + (s.days_in_month || 30) + ' ' + MONTHS[s.month_index || 10] + ' около ' + money(sp.forecast)) + '</span></div>' +
      '<div><div class="meter" role="img" aria-label="' + esc('Потрачено ' + money(sp.spent) + ' из ' + money(limit)) + '"><span class="meter__fill" style="width:' + Math.min(100, limit ? sp.spent / limit * 100 : 0) + '%"></span>' +
      (warn && limit ? '<span class="meter__mark" style="left:calc(' + (warn / limit * 100) + '% - 1px)"></span>' : '') + '</div>' +
      (warn && limit ? '<div class="meter__caption"><span style="left:' + (warn / limit * 100) + '%">' + t('предупреждение при ' + money(warn)) + '</span></div>' : '') + '</div>' +
      chart(s) + facts(s.spend_facts || []) + '<a class="link" href="#agent/settings">Лимит и предупреждение в настройках</a></section>';
    var year = ui.year || (s.years || [s.year])[0];
    left += '<section class="panel"><div class="panel__head panel__head--between"><h2 class="h2">Прошлые месяцы</h2><button class="select" type="button" data-act="year" aria-haspopup="menu" aria-expanded="false">' + esc(year) + IC.chev + '</button></div>' +
      '<table class="table"><thead><tr><th scope="col">Месяц</th><th scope="col">Обращений</th><th scope="col">Закрыл сам</th><th scope="col">Время менеджеров</th><th scope="col">Работа агента</th><th scope="col">Всего</th></tr></thead><tbody>' +
      (s.months || []).map(function (m) { return '<tr><td>' + t(m.name) + '</td><td>' + t(m.requests) + '</td><td>' + t(m.closed) + '</td><td>' + t(m.manager_time) + '</td><td>' + t(m.agent) + '</td><td>' + t(m.total) + '</td></tr>'; }).join('') +
      '</tbody></table><p class="panel__note">' + t('Всего = работа агента и сервер ' + money(s.server_rub || 0) + ' в месяц.') + '</p></section>';

    var right = '<section class="panel"><h2 class="h2">Состояние агента</h2>' + facts(s.health || []) +
      (s.outage ? '<div class="facts"><p class="medium">' + t('Сбои ' + (s.month_in || '')) + '</p><p>' + t(s.outage) + '</p></div>' : '') + '</section>';
    var total = s.reasons_total || 1;
    right += '<section class="panel"><div class="panel__head panel__head--between"><h2 class="h2">Почему передаёт менеджеру</h2><span class="tag">замер</span></div><div class="reasons">' +
      (s.reasons || []).map(function (x, i) {
        return '<div class="reason"><div class="reason__top"><span>' + t(x.title) + '</span><span>' + x.count + '</span></div><div class="reason__track"><div class="reason__fill" style="width:' + (x.count / total * 100) + '%;animation-delay:' + i * 40 + 'ms"></div></div>' +
          (x.note ? '<p class="muted">' + t(x.note) + '</p>' : '') + (x.link ? '<div><button class="link" type="button" data-act="gap-link" data-id="' + esc(x.gap || '') + '">' + t(x.link) + '</button></div>' : '') + '</div>';
      }).join('') + '</div><p class="panel__note">' + t(s.reasons_note || '') + '</p></section>';
    var b = benefit(), bb = ui.benefit;
    right += '<section class="panel"><div class="panel__head panel__head--between"><h2 class="h2">Выгода ' + esc(s.month_in || '') + '</h2><span class="tag">оценка</span></div>' +
      '<div><p class="num" data-b="net">' + money(Math.max(0, b.net)) + '</p><p class="muted">сэкономил магазину за вычетом расходов</p></div>' +
      '<div class="facts" data-b="facts">' + benefitFacts(b) + '</div>' +
      '<div class="facts" style="gap:12px"><label class="calc"><span>' + t((s.benefit || {}).minutes_hint || 'Минут на обращение') + '</span><input class="field field--num" inputmode="numeric" data-act="bmin" value="' + esc(bb.minutes) + '"></label>' +
      '<label class="calc"><span>' + t((s.benefit || {}).rate_hint || 'Час менеджера, ₽') + '</span><input class="field field--num" inputmode="numeric" data-act="brate" value="' + esc(group3(bb.rate)) + '"></label></div>' +
      '<p class="panel__note">' + t(s.benefit_note || '') + '</p></section>';
    return '<div class="agent-cols"><div class="col">' + left + '</div><div class="col">' + right + '</div></div>';
  }
  function benefitFacts(b) { return fact('Время менеджеров', '≈' + Math.round(b.hours) + ' ч') + fact('Расходы на агента', money(b.cost)) + fact('На 1 ₽ расходов', '≈' + group3(Math.round(b.per)) + ' ₽'); }
  function dayName(s, d) { var x = new Date(s.year || new Date().getFullYear(), s.month_index || 0, d); return d + ' ' + MONTHS[x.getMonth()] + ', ' + WEEKDAYS[x.getDay()]; }
  function barValue(s, d) { return d < s.today_day ? (s.days || [])[d - 1] || 0 : d === s.today_day ? s.today_rub || 0 : s.forecast_rub || 0; }
  function chart(s) {
    var n = s.days_in_month || 30, today = s.today_day || 1, vals = [];
    for (var d = 1; d <= n; d++) vals.push(barValue(s, d));
    var top = Math.max(1, Math.ceil(Math.max.apply(null, vals) - 0.15)), px = 135 / top;
    var grid = '';
    for (var g = 0; g <= top; g++) grid += '<span class="chart__grid" style="bottom:' + (g * px) + 'px"></span><span class="chart__y" style="bottom:' + (g * px - 10) + 'px;transform:none">' + (g ? g + ' ₽' : '0') + '</span>';
    var bars = vals.map(function (v, k) {
      var d = k + 1, cls = d < today ? '' : d === today ? ' bar--today' : ' bar--future';
      return '<span class="bar' + cls + '" tabindex="0" data-day="' + d + '" aria-label="' + esc(tipText(s, d).join(': ')) + '"><i style="height:' + Math.round(v * px) + 'px;animation-delay:' + k * 10 + 'ms"></i></span>';
    }).join('');
    var marks = [1, 5, 10, 15, 20, today, n].filter(function (v, k, a) { return a.indexOf(v) === k && (v === today || Math.abs(v - today) > 2); });
    var xs = marks.map(function (d) { return '<span' + (d === today ? ' class="is-today"' : '') + ' style="left:' + ((d - 0.5) / n * 100) + '%">' + d + '</span>'; }).join('');
    return '<div class="chart"><div class="chart__plot" style="height:' + (top * px + 4) + 'px">' + grid + '<div class="chart__bars">' + bars + '</div></div><div class="chart__x" aria-hidden="true">' + xs + '</div>' +
      '<div class="legend"><span class="legend__item"><span class="dot dot--accent"></span>Прошедшие дни <b>' + t(s.legend_past || '') + '</b></span>' +
      '<span class="legend__item"><span class="dot" style="background:var(--accent-hover)"></span>Сегодня <b>' + t(dec(s.today_rub || 0, 1) + ' ₽') + '</b></span>' +
      '<span class="legend__item"><span class="dot" style="background:rgba(0,122,255,.14)"></span>Прогноз <b>' + t(dec(s.forecast_rub || 0, 1) + ' ₽ в день') + '</b></span></div></div>';
  }
  function tipText(s, d) {
    var v = barValue(s, d);
    return [dayName(s, d), d < s.today_day ? dec(v, 1) + ' ₽ за день' : d === s.today_day ? dec(v, 1) + ' ₽ за сегодня, день ещё идёт' : 'прогноз ' + dec(v, 1) + ' ₽'];
  }

  function viewSettings() {
    var s = store.settings || {};
    var warnBad = s.warn_rub >= s.limit_rub;
    var limit = '<section class="panel"><h2 class="h2">Лимит на работу агента</h2><div class="fields">' +
      '<label class="label"><span class="label__text">Лимит в месяц, ₽</span><input class="field" inputmode="numeric" data-set="limit_rub" value="' + esc(group3(s.limit_rub)) + '"></label>' +
      '<label class="label"><span class="label__text">Предупредить при, ₽</span><input class="field' + (warnBad ? ' is-error' : '') + '" inputmode="numeric" data-set="warn_rub" value="' + esc(group3(s.warn_rub)) + '"' + (warnBad ? ' aria-invalid="true" aria-describedby="warnErr"' : '') + '></label></div>' +
      (warnBad ? '<p class="error-text" id="warnErr">Предупреждение должно быть меньше лимита</p>' : '') +
      '<p>' + rich('Когда лимит потрачен, агент **молчит до 1-го числа**, чаты идут менеджерам.\nО пороге менеджеры узнают **в кабинете' + (s.notify ? ' и уведомлением' : '') + '**.') + '</p></section>';
    var hours = '<section class="panel"><h2 class="h2">Срок ответа и часы менеджеров</h2><div class="fields fields--hours">' +
      '<label class="label"><span class="label__text">Ответ менеджера обещаем через, мин</span><input class="field" inputmode="numeric" data-set="answer_min" value="' + esc(s.answer_min) + '"></label>' +
      '<div class="label"><span class="label__text" id="hoursLabel">Часы менеджеров, по Москве</span><div class="hours" role="group" aria-labelledby="hoursLabel">' +
      '<button class="select" type="button" data-act="set-days" aria-haspopup="menu" aria-expanded="false" aria-label="Дни: ' + esc(s.days) + '">' + esc(s.days) + IC.chev + '</button>' +
      '<button class="select" type="button" data-act="set-from" aria-haspopup="menu" aria-expanded="false" aria-label="С ' + esc(s.from) + '">' + esc(s.from) + IC.chev + '</button><span class="muted" aria-hidden="true">–</span>' +
      '<button class="select" type="button" data-act="set-to" aria-haspopup="menu" aria-expanded="false" aria-label="До ' + esc(s.to) + '">' + esc(s.to) + IC.chev + '</button></div></div></div>' +
      '<p>' + rich('Этот срок агент **называет клиенту**, когда передаёт вопрос менеджеру.\nВечером и в выходные обещает ответ **до ' + hmOf(mins(s.from) + 60) + ' рабочего дня**.') + '</p></section>';
    var notify = '<section class="panel"><div class="panel__head panel__head--between"><h2 class="h2" id="notifyTitle">Уведомления менеджерам</h2><button class="switch" type="button" role="switch" aria-checked="' + !!s.notify + '" aria-labelledby="notifyTitle" data-act="notify"></button></div>' +
      '<p class="muted" style="margin-top:-8px">' + t('Пишем менеджеру, когда агент передаёт ему разговор') + '</p>' +
      '<div class="options options--2' + (s.notify ? '' : ' is-off') + '" role="radiogroup" aria-label="Куда писать">' + (s.channels || []).map(function (ch) {
        if (ch.off) return '<div class="option option--off" aria-disabled="true"><b>' + t(ch.name) + '</b><span>' + t(ch.note) + '</span></div>';
        var on = s.channel === ch.id;
        return '<button class="option' + (on ? ' is-selected' : '') + '" type="button" role="radio" aria-checked="' + on + '" data-act="channel" data-id="' + esc(ch.id) + '"' + (s.notify ? '' : ' disabled') + '><b>' + t(ch.name) + '</b><span>' + t(ch.note) + '</span></button>';
      }).join('') + '</div><p>' + rich(s.notify ? 'Уведомления **бесплатные** и лимит не тратят.' : 'Уведомления выключены: о новых разговорах менеджеры узнают **только в кабинете**.') + '</p></section>';
    var model = '<section class="panel"><h2 class="h2">Модель</h2><div class="options options--3" role="radiogroup" aria-label="Модель агента">' + (s.models || []).map(function (m) {
      var on = s.model === m.id;
      return '<button class="option' + (on ? ' is-selected' : '') + '" type="button" role="radio" aria-checked="' + on + '" data-act="model" data-id="' + esc(m.id) + '"><b>' + t(m.name) + '</b><span>' + t(m.cost) + '</span></button>';
    }).join('') + '</div><p>' + rich('Модель **меняется сразу**: следующие обращения агент разберёт уже на ней.') + '</p><p class="panel__note">' + t(s.model_note || '') + '</p></section>';
    return '<div class="settings-cols">' + limit + hours + notify + model + '</div>';
  }
  function saveSettings(patch, done) {
    var s = store.settings;
    return act('settings', 'PUT', '/agent/settings', patch, function (res) { Object.assign(s, res && typeof res === 'object' && res.limit_rub != null ? res : patch); })
      .then(function () { if (done) toast(done); render(); }, function () { render(); });
  }

  /* ---------- свои окна: меню и календарь под кнопкой ---------- */
  var pop = null;
  function openPop(anchor, html, opts) {
    closePop(true);
    opts = opts || {};
    var el = document.createElement('div');
    el.className = 'pop' + (opts.cls ? ' ' + opts.cls : '');
    el.setAttribute('role', opts.role || 'menu');
    el.innerHTML = html;
    $('#layer').appendChild(el);
    if (opts.width) el.style.width = opts.width + 'px';
    pop = { el: el, anchor: anchor, align: opts.align, data: opts.data || {} };
    anchor.setAttribute('aria-expanded', 'true');
    place();
    var first = $('[aria-checked="true"]', el) || $('.menu__item:not(:disabled), .cal__day.is-selected, .cal__day:not(:disabled)', el);
    if (first) { first.focus({ preventScroll: true }); if (opts.scrollTo !== false) first.scrollIntoView({ block: 'nearest' }); }
  }
  function place() {
    if (!pop) return;
    var r = pop.anchor.getBoundingClientRect(), el = pop.el, w = el.offsetWidth, h = el.offsetHeight;
    var left = pop.align === 'right' ? r.right - w : r.left;
    left = Math.max(8, Math.min(left, innerWidth - w - 8));
    var top = r.bottom + 8;
    if (top + h > innerHeight - 8 && r.top - 8 - h > 8) top = r.top - 8 - h;
    el.style.left = left + 'px'; el.style.top = top + 'px';
  }
  function closePop(instant, back) {
    if (!pop) return;
    var p = pop; pop = null;
    p.anchor.setAttribute('aria-expanded', 'false');
    if (back) p.anchor.focus();
    if (instant) p.el.remove();
    else { p.el.classList.add('is-closing'); setTimeout(function () { p.el.remove(); }, 160); }
  }
  function menu(items) {
    return items.map(function (i) {
      if (i === '-') return '<div class="menu__sep" role="separator"></div>';
      return '<button class="menu__item" type="button" role="' + (i.check != null ? 'menuitemradio' : 'menuitem') + '"' + (i.check != null ? ' aria-checked="' + !!i.check + '"' : '') +
        ' data-act="' + i.act + '" data-value="' + esc(i.value == null ? '' : i.value) + '"' + (i.disabled ? ' disabled' : '') + '><span>' + t(i.label) + '</span>' + (i.check ? IC.check.replace('currentColor', '#0070F0') : '') + '</button>';
    }).join('');
  }
  function calendar(month, selected) {
    var today = midnight(new Date()), y = month.getFullYear(), m = month.getMonth();
    var first = new Date(y, m, 1), shift = (first.getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
    var isCur = y === today.getFullYear() && m === today.getMonth();
    var h = '<div class="cal" role="dialog" aria-label="Выбор дня"><div class="cal__head"><button class="cal__nav" type="button" data-act="cal-prev" aria-label="Предыдущий месяц">' + IC.prev + '</button>' +
      '<b>' + MONTHS_1[m] + ' ' + y + '</b><button class="cal__nav" type="button" data-act="cal-next" aria-label="Следующий месяц"' + (isCur ? ' disabled' : '') + '>' + IC.next + '</button></div><div class="cal__grid">' +
      ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(function (d) { return '<span class="cal__wd">' + d + '</span>'; }).join('');
    for (var i = 0; i < shift; i++) h += '<span></span>';
    for (var d = 1; d <= days; d++) {
      var day = new Date(y, m, d), fut = day > today;
      h += '<button class="cal__day' + (sameDay(day, today) ? ' is-today' : '') + (sameDay(day, selected) ? ' is-selected' : '') + '" type="button" data-act="cal-day" data-value="' + day.getTime() + '"' + (fut ? ' disabled' : '') +
        ' aria-label="' + d + ' ' + MONTHS[m] + '"' + (sameDay(day, selected) ? ' aria-current="date"' : '') + '>' + d + '</button>';
    }
    return h + '</div></div>';
  }
  function dayMenu(anchor) {
    var today = midnight(new Date()), items = [];
    for (var b = 0; b < 4; b++) { var d = new Date(today); d.setDate(d.getDate() - b); items.push({ label: dayLabel(d), act: 'jday-pick', value: d.getTime(), check: sameDay(d, ui.jDay) }); }
    items.push('-', { label: 'Выбрать дату…', act: 'jcal' });
    openPop(anchor, menu(items), { width: 240 });
  }
  function timeMenu(anchor, key) {
    var s = store.settings, items = [];
    for (var m = 7 * 60; m <= 21 * 60; m += 30) {
      var v = hmOf(m), bad = key === 'from' ? m >= mins(s.to) : m <= mins(s.from);
      items.push({ label: v, act: 'set-time', value: key + '|' + v, check: s[key] === v, disabled: bad });
    }
    openPop(anchor, menu(items), { width: 160 });
  }

  /* ---------- свои окна: подтверждение поверх затемнения ---------- */
  var dialog = null;
  function openDialog(o) {
    closePop(true);
    var s = document.createElement('div');
    s.className = 'scrim';
    s.innerHTML = '<div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlgTitle"><h2 class="h2" id="dlgTitle">' + t(o.title) + '</h2>' +
      (o.text ? '<p class="dialog__text">' + rich(o.text) + '</p>' : '') + (o.body || '') +
      (o.error ? '<p class="error-text" id="dlgErr" hidden></p>' : '') +
      '<div class="dialog__buttons">' + (o.extra || '') + '<button class="btn btn--grey" type="button" data-act="dlg-cancel">' + t(o.cancel || 'Отмена') + '</button>' +
      (o.ok ? '<button class="btn btn--accent" type="button" data-act="dlg-ok"' + (o.okDisabled ? ' disabled' : '') + '>' + t(o.ok) + '</button>' : '') + '</div></div>';
    document.body.appendChild(s);
    dialog = { el: s, back: document.activeElement, o: o };
    s.addEventListener('mousedown', function (e) { if (e.target === s) closeDialog(); });
    var f = $('input, textarea', s) || $('[data-act="dlg-ok"]', s) || $('[data-act="dlg-cancel"]', s);
    if (f) { f.focus(); if (f.select && f.tagName === 'INPUT') f.select(); }
  }
  function closeDialog() {
    if (!dialog) return;
    var d = dialog; dialog = null;
    d.el.classList.add('is-closing');
    setTimeout(function () { d.el.remove(); }, 160);
    if (d.back && d.back.focus && document.contains(d.back)) d.back.focus();
  }
  function dialogError(text) { var e = $('#dlgErr'); if (e) { e.hidden = !text; e.textContent = text || ''; } var f = $('.dialog .field'); if (f) f.classList.toggle('is-error', !!text); }

  /* ---------- подсказка графика: после 300 мс наведения ---------- */
  var tipTimer = 0, tipEl = null;
  function showTip(bar) {
    hideTip();
    var s = store.stats, d = +bar.getAttribute('data-day'), txt = tipText(s, d);
    tipEl = document.createElement('div'); tipEl.className = 'tip'; tipEl.setAttribute('role', 'tooltip');
    tipEl.innerHTML = t(txt[0]) + '<span>' + t(txt[1]) + '</span>';
    document.body.appendChild(tipEl);
    var r = bar.getBoundingClientRect(), i = $('i', bar).getBoundingClientRect(), w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    tipEl.style.left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 8)) + 'px';
    tipEl.style.top = Math.max(8, i.top - h - 8) + 'px';
  }
  function hideTip() { clearTimeout(tipTimer); if (tipEl) { tipEl.remove(); tipEl = null; } }
  document.addEventListener('mouseover', function (e) {
    var bar = e.target.closest && e.target.closest('.bar');
    if (!bar) return;
    clearTimeout(tipTimer); tipTimer = setTimeout(function () { showTip(bar); }, 300);
  });
  document.addEventListener('mouseout', function (e) { if (e.target.closest && e.target.closest('.bar') && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.bar') === e.target.closest('.bar'))) hideTip(); });
  document.addEventListener('focusin', function (e) { if (e.target.classList && e.target.classList.contains('bar')) showTip(e.target); });
  document.addEventListener('focusout', function (e) { if (e.target.classList && e.target.classList.contains('bar')) hideTip(); });

  /* ---------- черновики полей переживают перерисовку ---------- */
  function restoreDrafts() {
    $$('[data-draft]').forEach(function (f) {
      var d = ui.drafts[f.getAttribute('data-id')], k = f.getAttribute('data-draft');
      if (d && d[k] != null && f.value !== d[k]) f.value = d[k];
      grow(f);
    });
  }
  // поле ответа растёт по тексту; где браузер не умеет field-sizing, высоту ставим сами
  var SIZES_ITSELF = window.CSS && CSS.supports && CSS.supports('field-sizing', 'content');
  function grow(f) {
    if (SIZES_ITSELF || f.tagName !== 'TEXTAREA' || !f.closest('.case, .talk')) return;
    f.style.height = 'auto';
    f.style.height = (f.scrollHeight + f.offsetHeight - f.clientHeight) + 'px';
  }
  function rerenderKeep(f) {
    var sel = '[data-act="' + f.getAttribute('data-act') + '"]', pos = f.selectionStart;
    render().then(function () { var n = $(sel); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} } });
  }
  document.addEventListener('input', function (e) {
    var f = e.target, k = f.getAttribute && f.getAttribute('data-draft');
    if (k) {
      var id = f.getAttribute('data-id'), d = ui.drafts[id] || (ui.drafts[id] = {});
      d[k] = f.value;
      grow(f);
      var scope = f.closest('.case, .talk, .dialog') || document;
      $$('[data-needs="' + k + '"]', scope).forEach(function (b) { b.disabled = !f.value.trim(); });
      return;
    }
    var a = f.getAttribute && f.getAttribute('data-act');
    if (a === 'jsearch') { ui.jQuery = f.value; rerenderKeep(f); }
    if (a === 'ksearch') { ui.kQuery = f.value; rerenderKeep(f); }
    if (a === 'discount') {
      var c = findCase(f.getAttribute('data-id')), v = num(f.value), bad = !(v >= 0 && v < 100) && f.value.trim() !== '';
      f.classList.toggle('is-error', bad); f.setAttribute('aria-invalid', bad);
      ui.discount[c.id] = bad || isNaN(v) ? 0 : v;
      var total = kpTotal(c), card = f.closest('.case');
      $('[data-kp="total"]', card).textContent = ty(rub2(total));
      var vat = $('[data-kp="vat"]', card); if (vat) vat.textContent = ty(rub2(total * 22 / 122));
      var pr = $('#price-' + c.id); if (pr) pr.textContent = money(total);
      $('[data-act="send-kp"]', card).disabled = bad;
    }
    if (a === 'bmin' || a === 'brate') {
      ui.benefit[a === 'bmin' ? 'minutes' : 'rate'] = num(f.value) || 0;
      var b = benefit();
      $('[data-b="net"]').textContent = money(Math.max(0, b.net));
      $('[data-b="facts"]').innerHTML = benefitFacts(b);
    }
  });
  document.addEventListener('change', function (e) {
    var f = e.target, key = f.getAttribute && f.getAttribute('data-set');
    if (!key) return;
    var s = store.settings, v = num(f.value);
    if (!(v > 0)) { f.classList.add('is-error'); toast('Введите число больше нуля'); return; }
    var patch = {}; patch[key] = Math.round(v);
    var next = Object.assign({}, s, patch);
    if (next.warn_rub >= next.limit_rub) { s[key] = patch[key]; render(); return; }
    var msg = key === 'limit_rub' ? 'Лимит сохранён: ' + money(v) + ' в месяц' : key === 'warn_rub' ? 'Предупредим при ' + money(v) : 'Агент будет обещать ответ менеджера через ' + Math.round(v) + ' мин';
    saveSettings(patch, msg);
  });

  /* ---------- клавиатура: Esc закрывает окна, стрелки ходят по меню ---------- */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (dialog) { e.preventDefault(); closeDialog(); return; }
      if (pop) { e.preventDefault(); closePop(false, true); return; }
    }
    if (dialog && e.key === 'Tab') {
      var fs = $$('button:not(:disabled), input, textarea', dialog.el); if (!fs.length) return;
      var i = fs.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); fs[fs.length - 1].focus(); }
      else if (!e.shiftKey && i === fs.length - 1) { e.preventDefault(); fs[0].focus(); }
    }
    if (dialog && e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); var ok = $('[data-act="dlg-ok"]', dialog.el); if (ok && !ok.disabled) ok.click(); }
    if (pop && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      var items = $$('.menu__item:not(:disabled)', pop.el); if (!items.length) return;
      e.preventDefault();
      var j = items.indexOf(document.activeElement);
      items[(j + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
    }
    if (pop && e.key === 'Tab') closePop(true);
    if (e.key === 'Enter' && e.target.getAttribute && e.target.getAttribute('data-set')) e.target.blur();
  });
  addEventListener('resize', function () { closePop(true); hideTip(); });
  addEventListener('scroll', function () { place(); if (tipEl) hideTip(); }, true);

  /* ---------- нажатия ---------- */
  document.addEventListener('mousedown', function (e) {
    if (pop && !pop.el.contains(e.target) && !pop.anchor.contains(e.target)) closePop();
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]');
    if (!b || b.disabled || b.tagName === 'INPUT') return;
    var a = b.getAttribute('data-act'), id = b.getAttribute('data-id'), val = b.getAttribute('data-value');
    var c = id ? findCase(id) : null;
    if (pop && b.closest('.pop') == null && b !== pop.anchor) closePop(true);

    switch (a) {
      /* Сегодня */
      case 'pick': ui.sel = id; render(); return;
      case 'kp-toggle': ui.kpClosed[id] = !ui.kpClosed[id]; render(); return;
      case 'edit-kp': ui.kpEdit[id] = true; ui.discount[id] = (c.kp && c.kp.discount) || 0; render().then(function () { var f = $('#disc-' + id); if (f) { f.focus(); f.select(); } }); return;
      case 'cancel-edit': ui.kpEdit[id] = false; ui.discount[id] = 0; render(); return;
      case 'send-kp': return sendKp(c, b);
      case 'export-csv': window.SupportBackend.downloadCases().catch(function () { toast('Не удалось выгрузить журнал'); }); return;
      case 'help': var dh = draft(c); dh.help = b.getAttribute('aria-checked') !== 'true'; b.setAttribute('aria-checked', dh.help); return;
      case 'answer': return answer(c, b);
      case 'return': return giveBack(c, b);
      case 'say': return say(c);
      case 'more': ui.talkAll[id] = !ui.talkAll[id]; render(); return;
      case 'goto-today': ui.sel = id; location.hash = '#today'; return;

      /* состояние агента */
      case 'pause':
        openDialog({ title: 'Поставить агента на паузу?', text: 'Новые чаты сразу пойдут менеджерам, без сводки агента. Включить агента можно тем же переключателем.', ok: 'Поставить на паузу',
          onOk: function () { setStatus({ state: 'paused', since: storyNow('status') }, 'Агент на паузе: новые чаты идут менеджерам'); } });
        return;
      case 'resume': setStatus({ state: 'on' }, 'Агент снова отвечает клиентам'); return;
      case 'limit':
        var st = store.settings || SAMPLE.settings, spent = spend().spent;
        openDialog({ title: 'Поднять лимит ' + ((store.stats || SAMPLE.stats).month_in || 'на месяц').replace(/^за /, 'на '), text: 'Потрачено ' + money(spent) + ' из ' + money(st.limit_rub) + '. Агент вернётся к чатам сразу после сохранения.',
          body: '<label class="label"><span class="label__text">Новый лимит, ₽</span><input class="field" inputmode="numeric" data-dlg="limit" value="' + esc(group3(st.limit_rub + 500)) + '" aria-describedby="dlgErr"></label>', error: true, ok: 'Поднять лимит',
          onOk: function () {
            var v = num($('[data-dlg="limit"]').value);
            if (!(v > spent)) { dialogError('Новый лимит должен быть больше ' + money(spent)); return false; }
            act('settings', 'PUT', '/agent/settings', { limit_rub: Math.round(v) }, function () { st.limit_rub = Math.round(v); if (st.warn_rub >= st.limit_rub) st.warn_rub = Math.round(st.limit_rub * 0.8); })
              .then(function () { setStatus({ state: 'on' }, 'Лимит поднят до ' + money(v) + ', агент снова отвечает'); });
          } });
        return;
      case 'dlg-cancel': closeDialog(); return;
      case 'dlg-ok': if (dialog && dialog.o.onOk && dialog.o.onOk() === false) return; closeDialog(); return;

      /* профиль */
      case 'profile':
        if (pop && pop.anchor === b) { closePop(); return; }
        openPop(b, '<div class="menu__head"><span class="medium">Антон</span><span class="muted">Менеджер Store, до 18:00</span></div><div class="menu__sep"></div>' + menu([{ label: 'Выйти', act: 'logout' }]), { width: b.offsetWidth, align: 'right' });
        return;
      case 'logout':
        closePop(true);
        if (DEMO) { location.href = '../'; return; }
        try { sessionStorage.removeItem('sl-manager-key'); } catch (err) {}
        location.reload(); return;

      /* Журнал */
      case 'jday': if (pop && pop.anchor === b) { closePop(); return; } dayMenu(b); return;
      case 'jday-pick': ui.jDay = new Date(+val); ui.jSel = null; closePop(false, true); render(); return;
      case 'jcal':
        var anchor = pop.anchor; ui.calMonth = new Date(ui.jDay.getFullYear(), ui.jDay.getMonth(), 1);
        pop.el.innerHTML = calendar(ui.calMonth, ui.jDay); pop.el.setAttribute('role', 'dialog'); pop.el.style.width = ''; place();
        var sd = $('.cal__day.is-selected', pop.el) || $('.cal__day:not(:disabled)', pop.el); if (sd) sd.focus();
        pop.anchor = anchor; return;
      case 'cal-prev': case 'cal-next':
        ui.calMonth = new Date(ui.calMonth.getFullYear(), ui.calMonth.getMonth() + (a === 'cal-prev' ? -1 : 1), 1);
        pop.el.innerHTML = calendar(ui.calMonth, ui.jDay); $('[data-act="' + a + '"]', pop.el).focus(); return;
      case 'cal-day': ui.jDay = new Date(+val); ui.jSel = null; closePop(false, true); render(); return;
      case 'jfilter': var key = b.getAttribute('data-key'); ui.jFilter = ui.jFilter === key ? null : key; ui.jSel = null; render(); return;
      case 'jgroup': ui.jOpen[b.getAttribute('data-key')] = b.getAttribute('data-open') !== 'true'; render(); return;
      case 'jpick': ui.jSel = id; render(); return;
      case 'jfix': case 'jok': return review(a, id);

      /* Знания */
      case 'kgroup': ui.kOpen[b.getAttribute('data-key')] = b.getAttribute('data-open') !== 'true'; render(); return;
      case 'kall': ui.kAll = true; render(); return;
      case 'kpending': return pendingDialog(id);
      case 'kgap': return gapDialog(id);
      case 'kfix': return fixDialog(id);
      case 'krule': return textDialog('rules', id, 'Правило агента', 'Сохранить правило', 'Правило сохранено, агент работает по нему со следующего обращения');
      case 'karticle': return textDialog('articles', id, 'Статья справки', 'Сохранить статью', 'Статья сохранена, агент отвечает по новому тексту');

      /* Агент */
      case 'gap-link': location.hash = '#knowledge'; setTimeout(function () { gapDialog(id); }, 60); return;
      case 'year':
        if (pop && pop.anchor === b) { closePop(); return; }
        var s = store.stats || {}, cur = ui.year || (s.years || [s.year])[0];
        openPop(b, menu((s.years || [s.year]).map(function (y) { return { label: String(y), act: 'year-pick', value: y, check: y === cur }; })), { width: 160, align: 'right' }); return;
      case 'year-pick': ui.year = +val; closePop(false, true); render(); return;
      case 'set-days':
        if (pop && pop.anchor === b) { closePop(); return; }
        openPop(b, menu(['Пн–пт', 'Пн–сб', 'Каждый день'].map(function (d) { return { label: d, act: 'set-days-pick', value: d, check: store.settings.days === d }; })), { width: 180 }); return;
      case 'set-days-pick': closePop(false, true); saveSettings({ days: val }, 'Часы менеджеров: ' + val + ', ' + store.settings.from + '–' + store.settings.to); return;
      case 'set-from': case 'set-to':
        if (pop && pop.anchor === b) { closePop(); return; }
        timeMenu(b, a === 'set-from' ? 'from' : 'to'); return;
      case 'set-time':
        var parts = val.split('|'), p = {}; p[parts[0]] = parts[1]; closePop(false, true);
        var ns = Object.assign({}, store.settings, p);
        saveSettings(p, 'Часы менеджеров: ' + ns.days + ', ' + ns.from + '–' + ns.to); return;
      case 'notify': var on = b.getAttribute('aria-checked') !== 'true'; saveSettings({ notify: on }, on ? 'Уведомления включены' : 'Уведомления выключены'); return;
      case 'channel': if (store.settings.channel !== id) saveSettings({ channel: id }, 'Уведомления пойдут в ' + byId(store.settings.channels, id).name); return;
      case 'model':
        if (store.settings.model === id) return;
        saveSettings({ model: id }, 'Модель изменена: ' + byId(store.settings.models, id).name); return;
    }
  });

  /* ---------- действия «Сегодня» ---------- */
  // в панели видны четыре последние реплики, остальные уходят под «Ещё N»
  function pushTalk(c, line) {
    c.talk = (c.talk || []).concat([line]);
    var over = c.talk.length - 4;
    if (over > 0) { c.talk_earlier = (c.talk_earlier || []).concat(c.talk.slice(0, over)); c.talk = c.talk.slice(over); }
  }
  // строка уезжает из очереди, потом открывается следующая
  function leave(c, then) {
    var row = $('.qrow[data-id="' + c.id + '"]');
    var next = queue().filter(function (x) { return x.id !== c.id && !x.owner; })[0];
    if (row) row.classList.add('is-leaving');
    setTimeout(function () { ui.sel = next ? next.id : null; then(); }, row ? 240 : 0);
  }
  function sendKp(c) {
    var d = ui.kpEdit[c.id] ? ui.discount[c.id] || 0 : 0;
    ui.busy[c.id] = true; render();
    act('cases', 'POST', '/cases/' + encodeURIComponent(c.id) + '/decision', { action: 'approve', discount_percent: d || undefined }, function (res) {
      if (res && res.id) Object.assign(c, res);
      c.status = 'done'; c.done_label = c.done_label || 'КП отправлено в ' + storyNow('cases');
      if (c.kp && d) c.kp.discount = d;
      if (isLocal('cases')) c.effect = (silent() ? 'Клиент получил' : 'Агент прислал') + ' в чат **КП файлом PDF**.' + (c.kp && c.kp.valid_until ? '\nЦена в КП действует **до ' + c.kp.valid_until + '**.' : '');
      if (c.sent && c.sent.talk) pushTalk(c, c.sent.talk);
    }).then(function () {
      delete ui.busy[c.id]; ui.kpEdit[c.id] = false;
      toast(d ? 'КП со скидкой ' + String(d).replace('.', ',') + '% отправлено клиенту в чат' : 'КП отправлено клиенту в чат');
      leave(c, render);
    }, function () { delete ui.busy[c.id]; render(); });
  }
  function answer(c) {
    var d = draft(c), text = String(d.reply || '').trim(), help = c.help_option && (DEMO ? d.help !== false : d.help === true);
    if (!text) return;
    ui.busy[c.id] = true; render();
    act('cases', 'POST', '/cases/' + encodeURIComponent(c.id) + '/decision', { action: 'answer', reply_text: text, add_to_help: help }, function (res) {
      if (res && res.id) Object.assign(c, res);
      if (!isLocal('cases')) return; // сервер закрывает обращение сразу: в чат менеджер не входит
      c.status = 'in-chat';
      pushTalk(c, { who: 'me', text: text, _new: true });
      if (c.in_chat) {
        c.steps = copy(c.in_chat.steps);
        if (text !== c.reply_draft) c.steps[c.steps.length - 1] = [storyNow('cases'), 'вы ответили клиенту'];
      }
      if (help && store.knowledge && store.knowledge.articles) store.knowledge.articles.unshift({ id: 'a-' + c.id, title: c.title, meta: 'Добавлена сегодня в ' + storyNow('cases') + ' из вашего ответа', text: text });
    }).then(function () {
      delete ui.busy[c.id]; delete ui.drafts[c.id];
      if (!isLocal('cases')) {
        c.status = 'done'; c.done_label = 'Ответ отправлен в ' + storyNow('cases');
        toast(c.knowledge && c.knowledge.saved ? 'Ответ отправлен и сохранён в знаниях' :
          c.knowledge && c.knowledge.reason ? 'Ответ отправлен. Сохранение отклонено: ' + c.knowledge.reason : 'Ответ отправлен клиенту в чат');
        leave(c, render); return;
      }
      toast(help ? 'Ответ отправлен клиенту и добавлен в справку' : 'Ответ отправлен клиенту, вы в чате');
      render();
      // клиент отвечает: видно, что разговор живой и агент ждёт, пока ему вернут чат
      if (c.in_chat && c.in_chat.client_reply) {
        setTimeout(function () { ui.typing[c.id] = true; if (ui.tab === 'today' && ui.sel === c.id) render(); }, 900);
        setTimeout(function () {
          ui.typing[c.id] = false; if (c.status !== 'in-chat') return;
          pushTalk(c, { who: 'client', text: c.in_chat.client_reply, _new: true }); c.first = c.in_chat.client_reply;
          if (ui.tab === 'today') render();
        }, 2600);
      }
    }, function () { delete ui.busy[c.id]; render(); });
  }
  function giveBack(c) {
    act('cases', 'POST', '/cases/' + encodeURIComponent(c.id) + '/return', null, function () {
      c.status = 'done'; c.done_label = 'Вернули агенту в ' + storyNow('cases');
      c.effect = 'Разговор снова ведёт агент.';
      c.talk.forEach(function (l) { delete l._new; });
    }).then(function () {
      toast(c.id === 'discount' ? 'Разговор у агента: он соберёт КП со скидкой 8% и пришлёт вам на проверку' : 'Разговор вернулся к агенту');
      leave(c, render);
    }, function () {});
  }
  function say(c) {
    var d = ui.drafts['say-' + c.id], text = d && d.say.trim();
    if (!text) return;
    act('cases', 'POST', '/cases/' + encodeURIComponent(c.id) + '/messages', { text: text }, function () {
      c.talk.forEach(function (l) { delete l._new; });
      pushTalk(c, { who: 'me', text: text, _new: true });
    }).then(function () { d.say = ''; render().then(function () { var b = $('#talk-' + c.id); if (b) b.lastElementChild && b.lastElementChild.scrollIntoView({ block: 'nearest' }); }); }, function () {});
  }
  function setStatus(next, msg) {
    act('status', 'POST', '/agent/pause', { paused: next.state === 'paused' }, function () { store.status = next; }).then(function () { toast(msg); renderTop(); render(); }, function () {});
  }

  /* ---------- проверка разговора из журнала ---------- */
  function review(a, id) {
    var it = jItemsFor(ui.jDay).filter(function (i) { return i.id === id; })[0], c = it && it.detail;
    var fix = a === 'jfix' ? ((ui.drafts['fix-' + id] || {}).fix || '').trim() : '';
    if (!c || (a === 'jfix' && !fix)) return;
    act('journal', 'POST', '/journal/' + encodeURIComponent(id) + '/review', fix ? { fix: fix } : { ok: true }, function () {
      it.review = false; it.status = { tone: 'success', text: fix ? 'Поправка сохранена' : 'Проверено' };
      c.status = 'done'; c.done_label = fix ? 'Поправка сохранена в ' + storyNow('journal') : 'Проверено в ' + storyNow('journal');
      c.effect = fix ? 'Агент запомнил поправку: «' + fix + '». Она во вкладке «Знания».' : 'Вы отметили, что агент ответил верно.';
      if (fix && store.knowledge && store.knowledge.fixes) store.knowledge.fixes.unshift({ id: 'f-' + id, title: fix, meta: 'Вы поправили сегодня, разговор с ' + it.client });
    }).then(function () { delete ui.drafts['fix-' + id]; toast(fix ? 'Поправка сохранена, она во вкладке «Знания»' : 'Отметили: агент ответил верно'); render(); }, function () {});
  }

  /* ---------- окна «Знаний» ---------- */
  function kStore() { return store.knowledge || (store.knowledge = copy(SAMPLE.knowledge)); }
  function addArticle(title, text, how) {
    var k = kStore(); k.articles = k.articles || [];
    k.articles.unshift({ id: 'a-' + Date.now(), title: title, meta: how + ' сегодня', text: text });
  }
  function pendingDialog(id) {
    var k = kStore(), p = byId(k.pending, id); if (!p) return;
    openDialog({ title: 'Добавить ответ в справку', text: p.title + '\n' + p.meta + '. Текст можно поправить, агент будет отвечать по нему сам.',
      body: '<textarea class="field" rows="4" data-dlg="text" aria-label="Текст ответа">' + esc(p.text || '') + '</textarea>', ok: 'Добавить в справку',
      onOk: function () {
        var txt = $('[data-dlg="text"]').value.trim(); if (!txt) { $('[data-dlg="text"]').classList.add('is-error'); return false; }
        act('knowledge', 'POST', '/knowledge/pending/' + encodeURIComponent(id) + '/add', { text: txt }, function () { k.pending = without(k.pending, id); addArticle(p.title, txt, 'Добавлена'); })
          .then(function () { toast('Ответ добавлен в справку'); render(); }, function () {});
      } });
  }
  function gapDialog(id) {
    var k = kStore(), g = byId(k.gaps, id); if (!g) return;
    openDialog({ title: 'Дописать справку: ' + g.title, text: g.share + ' передач менеджеру. Напишите, что агент должен отвечать на такие вопросы.',
      body: '<textarea class="field" rows="4" data-dlg="text" data-draft="gap" data-id="gap-' + esc(id) + '" placeholder="Например: цену серверной лицензии называет менеджер, агент собирает число пользователей и срок" aria-label="Текст статьи"></textarea>', ok: 'Добавить в справку', okDisabled: true,
      onOk: function () {
        var txt = $('[data-dlg="text"]').value.trim(); if (!txt) return false;
        act('knowledge', 'POST', '/knowledge/articles', { title: g.title, text: txt }, function () { k.gaps = without(k.gaps, id); addArticle(g.title, txt, 'Добавлена'); })
          .then(function () { toast('Статья добавлена, агент будет отвечать по ней'); render(); }, function () {});
      } });
    var ta = $('[data-dlg="text"]'), ok = $('[data-act="dlg-ok"]');
    ta.addEventListener('input', function () { ok.disabled = !ta.value.trim(); });
  }
  function fixDialog(id) {
    var k = kStore(), f = byId(k.fixes, id); if (!f) return;
    openDialog({ title: 'Поправка из проверки', text: f.meta + '. Сделайте её правилом, и агент будет работать по ней во всех разговорах.',
      body: '<textarea class="field" rows="3" data-dlg="text" aria-label="Текст правила">' + esc(f.title) + '</textarea>', ok: 'Сделать правилом',
      extra: '<button class="btn btn--grey" type="button" data-act="dlg-extra" style="margin-right:auto">Убрать</button>',
      onOk: function () {
        var txt = $('[data-dlg="text"]').value.trim(); if (!txt) return false;
        act('knowledge', 'POST', '/knowledge/fixes/' + encodeURIComponent(id) + '/rule', { text: txt }, function () { k.fixes = without(k.fixes, id); k.rules.unshift({ id: 'r-' + id, title: txt, meta: 'Из проверки разговора, добавлено сегодня' }); })
          .then(function () { toast('Правило добавлено, агент работает по нему'); render(); }, function () {});
      } });
    $('[data-act="dlg-extra"]').addEventListener('click', function () {
      act('knowledge', 'DELETE', '/knowledge/fixes/' + encodeURIComponent(id), null, function () { k.fixes = without(k.fixes, id); })
        .then(function () { closeDialog(); toast('Поправка убрана'); render(); }, function () {});
    });
  }
  function textDialog(list, id, title, okText, done) {
    var k = kStore(), x = byId(k[list], id); if (!x) return;
    var isRule = list === 'rules';
    openDialog({ title: title, text: isRule ? x.meta : x.title + '. ' + x.meta + '.',
      body: '<textarea class="field" rows="' + (isRule ? 3 : 5) + '" data-dlg="text" placeholder="' + (isRule ? '' : 'Текст статьи, по нему отвечает агент') + '" aria-label="' + esc(title) + '">' + esc(isRule ? x.title : x.text || '') + '</textarea>', ok: okText,
      onOk: function () {
        var txt = $('[data-dlg="text"]').value.trim(); if (isRule && !txt) return false;
        act('knowledge', 'PUT', '/knowledge/' + list + '/' + encodeURIComponent(id), { text: txt }, function () { if (isRule) x.title = txt; else x.text = txt; x.meta = isRule ? 'Вы изменили сегодня' : 'Обновлена сегодня'; })
          .then(function () { toast(done); render(); }, function () {});
      } });
  }

  /* ---------- обновление с сервера ---------- */
  // на «Сегодня» новые случаи приходят без перезагрузки; пока менеджер печатает или открыто окно, экран не трогаем
  var lastCases = '';
  function refresh() {
    if (DEMO || !store.role) return;
    if (ui.tab !== 'today' && ui.tab !== 'journal') return;
    var busy = pop || dialog || (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName));
    call('GET', '/cases').then(function (d) {
      var sig = JSON.stringify((d.cases || []).map(function (c) { return c.id + c.version + c.status; }));
      if (sig === lastCases) return; lastCases = sig;
      var old = {}; cases().forEach(function (c) { old[c.id] = c; });
      store.cases = d;
      cases().forEach(function (c) { var o = old[c.id]; if (o) ['talk', 'talk_earlier', 'steps', 'cost'].forEach(function (k) { if (c[k] == null && o[k] != null) c[k] = o[k]; }); });
      if (!busy) render(); else renderTop();
    }, function () {});
  }

  window.addEventListener('hashchange', route);
  store.status = DEMO ? copy(SAMPLE.status) : { state: 'on' };
  if (!DEMO) store.sample.status = true;
  if (VARIANT === 'limit') store.status = { state: 'limit', since: '10:07' };
  if (VARIANT === 'paused') store.status = { state: 'paused', since: '10:07' };
  if (VARIANT === 'empty') {
    loadToday().then(function () {
      cases().forEach(function (c) { c.status = 'done'; c.done_label = 'Закрыт'; });
      route();
    });
  } else route();
  setInterval(refresh, 5000);
})();
