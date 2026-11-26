/* Копия чата магазина (Webim) с агентом.
   По умолчанию чат говорит с агентом на сервере (запросы переводит api.js, адрес в config.js).
   ?demo или #demo: сценарий без сервера. #now: чат как сейчас (меню из шести тем и менеджер).
   #offhours: сценарий вечером и в выходные. #cards: шаг 2, свой виджет поверх Webim. */
(function () {
  var TOPICS = ['Выставить счёт', 'Тендер или госзакупка', 'Статус заказа и документы',
    'Ключ, активация, техническая поддержка', 'Google WorkSpace', 'Задать вопрос'];
  var BOT = 'Помощник Softline';
  var MANAGER = { name: 'Антон', role: 'Менеджер Store' }; // вымышленный менеджер вместо настоящего сотрудника
  var MANAGER_DELAY = 2500; // на сайте менеджер подключается примерно через 3 минуты

  var I = {
    star: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.6l2.9 5.9 6.5.95-4.7 4.6 1.1 6.5L12 17.48l-5.8 3.07 1.1-6.5-4.7-4.6 6.5-.95z"/></svg>',
    xs: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1.5 1.5l11 11M12.5 1.5l-11 11" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    webim: '<svg class="slc-credit__logo" viewBox="41.8 129 909.3 220.3" role="img" aria-label="Webim"><g><path fill="#393F6B" d="M453.9,219.4c32.5,0,56,24.1,56,56.6c0,2.2-0.3,6.2-0.6,8.4c-0.3,3.1-2.8,5.3-5.6,5.3h-89 c1.2,20.7,19.5,40.2,41.4,40.2c13,0,23.5-4.9,30.6-9.3c4.3-2.5,6.2-4,8.7-0.6c1.9,2.5,3.4,4.6,5.3,7.1c2.2,2.8,3.4,4.6-1.2,8 c-7.4,5.9-24.1,14.2-45.4,14.2c-37.4,0-60.6-29.4-60.6-64.9C393.3,249.4,416.5,219.4,453.9,219.4z M488.5,272.3 c-0.9-17.9-15.8-34-34.6-34c-20.7,0-36.8,14.8-39,34H488.5z"/><path fill="#393F6B" d="M543.9,135.6c0-3.1,2.8-5.9,5.9-5.9h9.6c3.1,0,5.9,2.8,5.9,5.9v91.8c0,0,12.7-8,33.1-8 c37.1,0,59.4,28.4,59.4,64.6c0,35.6-24.7,65.2-56.3,65.2c-23.2,0-38-16.4-38-16.4l-1.9,8.3c-0.6,2.8-2.5,4.9-5.3,4.9h-6.5 c-3.1,0-5.9-2.8-5.9-5.9V135.6z M599.2,329.8c22.6,0,36.8-21.3,36.8-45.4c0-24.7-13.6-44.2-40.5-44.2c-17,0-30,7.4-30,7.4v61.8 C565.5,309.4,577,329.8,599.2,329.8z"/><path fill="#393F6B" d="M688.3,150.8c0-8.3,6.5-14.8,14.5-14.8c8.3,0,14.8,6.5,14.8,14.8c0,8-6.5,14.5-14.8,14.5 C694.8,165.3,688.3,158.8,688.3,150.8z M692.6,228.4c0-3.1,2.8-5.9,5.9-5.9h9.6c3.1,0,5.9,2.8,5.9,5.9v111.9c0,3.1-2.8,5.9-5.9,5.9 h-9.6c-3.1,0-5.9-2.8-5.9-5.9V228.4z"/><path fill="#393F6B" d="M757.8,228.4c0-3.1,2.8-5.9,5.9-5.9h5.9c2.8,0,4.3,1.2,4.9,3.7l2.8,9.6c0,0,14.5-16.4,40.2-16.4 c18.2,0,31.5,7.1,39.6,20.1c1.5-1.2,21.3-20.1,46.1-20.1c35.9,0,47.9,23.5,47.9,55.6v65.2c0,3.1-2.8,5.9-5.9,5.9h-9.9 c-3.1,0-5.9-2.8-5.9-5.9V275c0-23.2-9.9-34.9-27.8-34.9c-20.1,0-33.4,13.3-37.7,17.3c0.9,5.3,1.5,11.1,1.5,17.6v65.2 c0,3.1-2.8,5.9-5.9,5.9h-9.9c-3.1,0-5.9-2.8-5.9-5.9V275c0-23.5-10.5-34.9-29.4-34.9c-21.9,0-35.2,17.6-35.2,17.6v82.5 c0,3.1-2.8,5.9-5.9,5.9h-9.6c-3.1,0-5.9-2.8-5.9-5.9V228.4H757.8z"/></g><linearGradient id="slcWebimG" gradientUnits="userSpaceOnUse" x1="39.8548" y1="320.8183" x2="220.2" y2="320.8183" gradientTransform="matrix(1 0 0 -1 2 538)"><stop offset="0" style="stop-color:#4AE1D2"/><stop offset="1" style="stop-color:#2E3280"/></linearGradient><path fill="url(#slcWebimG)" d="M183.1,170.6c-2.1,3.9-4,8.4-6.1,13.3c-1.8,4.3-3.4,8.7-4.9,12.9l-4.1,12.8c-2.5,8.4-5,15.8-7.6,22.5 c-2.8,7.4-5.9,14.1-9.1,20c-2.5,4.5-6.3,10.7-10.9,14.9c-4.1,3.6-7.7,5.1-11.9,5.1c-4.1-0.1-9-2.3-13.8-6.3 c-3.8-3.1-7.8-7.4-12.5-13.5c-3.6-4.8-7.3-10.3-11-16.4c-6.1-10.5-12.2-22.2-18.2-35c-11.2-24-18.5-44.7-25-62.2l0,0 c-0.3-1-1-1.7-1.9-2.1c-0.3-0.1-0.7-0.2-1.1-0.2c-0.9,0-1.7,0.2-2.3,0.8c-0.5,0.6-1,1.4-0.8,2.4c0.2,0.7,0.3,1.3,0.5,2 c4.6,18.2,11.1,41.7,20.4,67.4c3.9,10.6,9.3,24.7,16.4,38.9c3.6,7.2,7.2,13.6,11,19.5c4.7,7.4,9.4,13.2,14.6,18.2 c3.2,3.1,6.4,5.5,9.7,7.5c4.1,2.4,8,3.9,11.8,4.5c4.3,0.7,8.9,0.4,13.1-1c4-1.3,7.9-3.4,11.9-6.5c7.9-6.3,13.3-14.2,17.2-20.4 c4.1-6.6,7.8-13.8,11.9-23.5c3.1-7.4,6.2-15.5,9.3-24.8l4-11.4c1.4-3.8,2.9-7.3,4.3-10.8c7.1-18.5,16.6-19.3,24.2-6.7 C208.2,167,183.1,170.6,183.1,170.6z"/><path fill="#393F6B" d="M371.4,129c-3.6,0-6.5,2.5-7.6,5.9l-0.4,1.8l-3.9,19.3c-1.2,6.4-2.7,13.2-4.2,19.9l-0.7,3.4 c-3.5,15.9-7.2,32-11.2,47.9c-4.2,17-8.9,33.1-13.7,47.7c-2.8,8.5-5.7,16-8.6,22.3c-1.6,3.5-3.2,6.8-5,9.7 c-1.8,2.9-7.8,15.6-16.9,1.3c-1.6-2.5-3.4-5.5-5.4-9.3c-7.2-14.2-13.6-31.5-19.1-46.5l-4.1-11.2c-4.2-11.6-8.5-23.5-13.3-35.4 c-0.5-1.2-1-2.4-1.5-3.6c-3.1-7.5-6.9-16.3-11.6-25.3c-2.6-4.9-5.1-8.9-7.6-12.6c-2.7-3.8-6-8.1-11.1-12c-2.8-2-5.5-3.5-8.3-4.3 c-3.2-1-6.8-1.1-10-0.4c-3,0.7-6,2-8.9,4.1c-2.7,1.9-4.7,4-6.6,6.1c-3.9,4.6-6.6,9.1-8.7,13c0,0,24.4-3.4,39,21.5 c0.2,0.3,0.3,0.5,0.5,0.8c0.4,0.8,0.9,1.6,1.3,2.4c2.9,6,6.3,12.9,10,22.1c4.4,11,8.6,22.3,13,34.3c1.8,4.9,3.6,9.8,5.4,14.7 c2.8,7.5,6.2,16.4,9.8,25.2c2.8,6.9,6.7,16.1,11.6,25.2c1.9,3.4,4.4,8,7.6,12.5c2.6,3.7,6,8.1,10.8,12c2.6,2,5.2,3.5,7.9,4.5 c3.1,1.2,6.6,1.6,9.7,1.1c3.9-0.5,7.1-2.1,9.1-3.4c2.5-1.6,4.9-3.6,6.8-5.7c4.2-4.5,6.9-9.1,9.2-13.1c2.2-4,4.3-8.3,6.3-13.1 c3.2-7.8,6.2-16,9.2-26c5.4-17.7,9.3-35,12.7-51.2c3.1-14.5,6-30.3,9.3-49.7l0.7-4c1.1-6.8,2.2-13.4,3.2-20.3l2.9-20.7l0.4-2.8 c0-0.1,0-0.1,0-0.2C379.3,132.7,375.8,129,371.4,129z"/></svg>',
    bubble: '<svg viewBox="0 0 30 28" aria-hidden="true"><path fill="#c8134c" d="M6 0h18a6 6 0 0 1 6 6v11a6 6 0 0 1-6 6H9.5L2.6 27.4A1.2 1.2 0 0 1 .8 26.4L1.5 21A6 6 0 0 1 0 17V6a6 6 0 0 1 6-6z"/><rect x="7" y="5.2" width="16" height="2.6" rx="1.3" fill="#fff"/><rect x="7" y="10.2" width="16" height="2.6" rx="1.3" fill="#fff"/><rect x="13" y="15.2" width="10" height="2.6" rx="1.3" fill="#fff"/></svg>',
    sofl: '<svg viewBox="0 0 44 44" aria-hidden="true"><defs><clipPath id="slcSoflC"><circle cx="22" cy="22" r="22"/></clipPath></defs><g clip-path="url(#slcSoflC)"><rect width="44" height="44" fill="#fff"/><g transform="scale(0.45263) translate(-421.55 -16.81)"><path d="M472.79 68.06v45.98h45.97V68.06z" fill="#A6A8AB"/><path d="M421.55 16.81V62.8h45.98V16.81z" fill="#A20C33"/><path d="M472.79 16.81V62.8h45.97V16.81z" fill="#A6A8AB"/><path d="M421.55 68.06v45.98h45.98V68.06z" fill="#A6A8AB"/><path d="M438.87 80.92v9.4h13.53v3.31h-13.53v10.9h-3.85V77.57h19.03v3.35z" fill="#FFFFFF"/><path d="M486.55 77.57h3.85v23.61H505v3.35h-18.45z" fill="#FFFFFF"/><path d="m434.16 50.2 1.42-3.01c2 1.81 5.43 3.12 8.9 3.12 4.66 0 6.67-1.81 6.67-4.16 0-6.59-16.34-2.43-16.34-12.44 0-4.16 3.24-7.71 10.32-7.71 3.16 0 6.43.85 8.67 2.39l-1.27 3.08c-2.35-1.5-5.01-2.2-7.4-2.2-4.58 0-6.55 1.93-6.55 4.28 0 6.59 16.33 2.47 16.33 12.37 0 4.12-3.31 7.67-10.44 7.67-4.12 0-8.17-1.39-10.32-3.39Z" fill="#FFFFFF"/><path d="M505.82 39.8c0-5.97-4.28-10.36-10.01-10.36s-10.08 4.39-10.08 10.36 4.28 10.36 10.08 10.36 10.01-4.39 10.01-10.36m-23.78 0c0-7.9 5.84-13.79 13.78-13.79s13.7 5.86 13.7 13.79-5.84 13.79-13.7 13.79-13.78-5.89-13.78-13.79" fill="#FFFFFF"/></g></g></svg>',
    dots: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="4" r="1.9" fill="#fff"/><circle cx="10" cy="10" r="1.9" fill="#fff"/><circle cx="10" cy="16" r="1.9" fill="#fff"/></svg>',
    close: '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M2 2l14 14M16 2L2 16" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/></svg>',
    mute: '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#fff" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M2 7h3l4-3.5v11L5 11H2z"/><path d="M12 7l4 4M16 7l-4 4" stroke-linecap="round"/></svg>',
    mail: '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#fff" stroke-width="1.4" aria-hidden="true"><rect x="2" y="4" width="14" height="10" rx="1"/><path d="M2.5 4.5L9 10l6.5-5.5M2.5 13.5l5-4.5M15.5 13.5l-5-4.5"/></svg>',
    pen: '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#fff" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M3 15l1-4 8.5-8.5 3 3L7 14z"/><path d="M11 4l3 3"/></svg>',
    clip: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M15.5 9.5l-6 6a4 4 0 0 1-5.7-5.7l6.6-6.6a2.7 2.7 0 0 1 3.8 3.8l-6.5 6.5a1.3 1.3 0 0 1-1.9-1.9L12 5.4"/></svg>',
    smile: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="10" cy="10" r="8"/><circle cx="7.3" cy="8" r=".6" fill="currentColor"/><circle cx="12.7" cy="8" r=".6" fill="currentColor"/><path d="M6.5 11.8a4 4 0 0 0 7 0" stroke-linecap="round"/></svg>',
    send: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M18 2L2 9l6 2.5L10.5 18z"/><path d="M18 2L8 11.5"/></svg>',
    share: '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M9 3.5V6C4.5 6.3 2.5 9 2 12.5 3.5 10.4 5.6 9.6 9 9.6V12l5-4.3z"/></svg>',
    checks: '<svg width="14" height="9" viewBox="0 0 14 9" fill="none" stroke="#29a8e0" stroke-width="1.3" stroke-linecap="round" aria-hidden="true"><path d="M1 4.8l2.6 2.6L9 1.8M5.6 7.4L11.4 1.6"/></svg>',
    person: '<svg viewBox="0 0 44 44" fill="none" aria-hidden="true"><g clip-path="url(#slcPersonC)"><path d="M44 22c0 6.812-3.096 12.9-7.957 16.936-3.81 3.163-14.511-6.638-14.511-6.638s-9.765 9.8-13.575 6.638C3.096 34.901 0 28.812 0 22 0 9.85 9.85 0 22 0s22 9.85 22 22z" fill="#068AB4"/><path fill-rule="evenodd" clip-rule="evenodd" d="M7.768 38.777c3.503-2.148 7.372-3.618 9.021-3.88 1.04-.166 1.063-3.024 1.063-3.024s-3.054-3.024-3.72-7.09c-1.791 0-2.897-4.324-1.106-5.845-.006-.136-.028-.34-.056-.6C12.67 15.55 11.683 6.37 22 6.37c10.318 0 9.33 9.183 9.03 11.97-.028.26-.05.463-.056.6 1.79 1.52.685 5.843-1.106 5.843-.666 4.067-3.72 7.09-3.72 7.09s.023 2.859 1.063 3.025c1.649.262 5.518 1.733 9.021 3.88A21.913 21.913 0 0122 44a21.913 21.913 0 01-14.232-5.223z" fill="#E7ECED"/></g><defs><clipPath id="slcPersonC"><path fill="#fff" d="M0 0h44v44H0z"/></clipPath></defs></svg>'
  };
  I.doc = '<svg width="28" height="34" viewBox="0 0 28 34" aria-hidden="true"><path d="M1.5 4a3 3 0 0 1 3-3H17l9 9v20a3 3 0 0 1-3 3H4.5a3 3 0 0 1-3-3z" fill="#fff" stroke="#c9ccd3"/><path d="M17 1v6a3 3 0 0 0 3 3h6" fill="none" stroke="#c9ccd3"/><rect x="6" y="18" width="16" height="2" rx="1" fill="#c60b46"/><rect x="6" y="23" width="12" height="2" rx="1" fill="#c9ccd3"/></svg>';

  // Режим: по умолчанию чат с агентом; index.html#now показывает чат как сейчас (меню и менеджер)
  var MODE = /now/.test(location.hash) ? 'now' : 'agent';
  // Окно всегда как у Webim на сайте (chat-now.css): агент живёт внутри него как бот Webim.
  // Свой вид окна (chat.css: карточки, полужирный, микрофон) только для шага 2, по адресу с #cards
  var NEW = MODE === 'agent' && /cards/.test(location.hash);
  if (!NEW) { var css = document.querySelector('link[href$="chat/chat.css"]'); if (css) css.href = css.href.replace('chat.css', 'chat-now.css'); }
  else TOPICS = TOPICS.map(function (t) { return t === 'Google WorkSpace' ? 'Google Workspace' : t; });
  var AV = { agent: '<span class="slc-av slc-av--body">' + I.sofl + '</span>', manager: '<span class="slc-av slc-av--body">' + I.person + '</span>' };
  function avHtml(a) { return NEW ? (a === I.person ? AV.manager : AV.agent) : a; }
  I.bubble2 = '<svg viewBox="0 0 28 26" aria-hidden="true"><path d="M4 1h20a3 3 0 0 1 3 3v13a3 3 0 0 1-3 3H11l-6 5v-5H4a3 3 0 0 1-3-3V4a3 3 0 0 1 3-3z" fill="#c60b46"/><path d="M8 8h12M8 13h8" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>';
  I.mic = '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><rect x="6.25" y="1.75" width="5.5" height="9" rx="2.75"/><path d="M3.5 8.5a5.5 5.5 0 0 0 11 0M9 14v2.5"/></svg>';
  I.x = '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 4l10 10M14 4L4 14"/></svg>';
  I.play = '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" fill="#fff"/></svg>';
  I.arrow = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var AGENT = MODE === 'agent';
  // Живой режим: ответы приходят от агента на сервере. Сценарий без сервера остаётся для #demo, #offhours и #cards
  var CFG = window.SUPPORT_CONFIG || {};
  var LIVE = AGENT && !NEW && !CFG.demo && !/demo|offhours/.test(location.hash) && !/[?&]demo\b/.test(location.search);
  var API = String(CFG.apiBase || '/support/api').replace(/\/$/, '');
  var AGENT_ROLE = 'ИИ-помощник';

  // Каталог: цены с главной страницы магазина
  var CAT = {
    kesRenew: { name: 'Kaspersky Endpoint Security для бизнеса Стандартный, продление лицензии на 1 год, 1 узел', short: 'Kaspersky Endpoint Security Стандартный, продление', price: 2322, unit: 'node' },
    kes: { name: 'Kaspersky Endpoint Security для бизнеса Стандартный, новая лицензия на 1 год, 1 узел', short: 'Kaspersky Endpoint Security Стандартный, новая лицензия', price: 3318.21, unit: 'node' },
    cpYear: { name: 'КриптоПро CSP 5.0, годовая лицензия на 1 рабочее место', short: 'КриптоПро CSP 5.0 годовая', price: 1850, unit: 'place' },
    cpPerm: { name: 'КриптоПро CSP 5.0, бессрочная лицензия на 1 рабочее место', short: 'КриптоПро CSP 5.0 бессрочная', price: 3700, unit: 'place' },
    astra: { name: 'Astra Linux Special Edition 1.8 «Орёл», для рабочей станции, с обновлениями на 12 месяцев', short: 'Astra Linux Special Edition 1.8, рабочая станция', price: 12000, unit: 'lic' }
  };
  // Прошлый заказ компании Ольги: агент находит его по ИНН (данные демо)
  var RENEW = { no: '2411-0457', sent: '26 ноября', what: 'Kaspersky Endpoint Security Стандартный, продление, 40\u00a0узлов' }; // заказ на продление после оплаты
  var ORDER = { no: '1512-0388', date: '15.12.2025', what: 'Kaspersky Endpoint Security Стандартный, 40\u00a0узлов', nodes: 40, until: '15\u00a0декабря 2026', mail: 'o•••@•••.ru' };

  function el(html) { var d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; }
  function two(n) { return ('0' + n).slice(-2); }
  function hhmm() { var d = new Date(); return two(d.getHours()) + ':' + two(d.getMinutes()); }
  function ddmm(d) { d = d || new Date(); return two(d.getDate()) + '.' + two(d.getMonth() + 1); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  // неразрывный пробел после коротких слов и перед ₽, чтобы предлоги не висели в конце строки
  function ty(s) { return s.replace(/(^|[\s(«*])([А-Яа-яЁёA-Za-z]{1,2}|№|•)\s/g, '$1$2 ').replace(/(^|[\s(«*])([А-Яа-яЁёA-Za-z]{1,2})\s/g, '$1$2 ').replace(/\s₽/g, ' ₽'); }
  function money(v) {
    var r = Math.round(v * 100) / 100, int = Math.floor(r), kop = Math.round((r - int) * 100);
    return String(int).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + (kop ? ',' + two(kop) : '') + ' ₽';
  }
  function plural(n, one, few, many) { var a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many; }
  function units(item, q) { return q + '\u00a0' + (item.unit === 'node' ? plural(q, 'узел', 'узла', 'узлов') : item.unit === 'lic' ? plural(q, 'лицензия', 'лицензии', 'лицензий') : plural(q, 'место', 'места', 'мест')); }
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  function dayMonth(d) { return d.getDate() + ' ' + MONTHS[d.getMonth()]; }
  function plusDays(n) { var d = new Date(); d.setDate(d.getDate() + n); return d; }

  var EMOJI = ['👍', '🙏', '😊', '🙂', '😉', '👌', '✅', '❗', '🤝', '👋', '😀', '🤔', '😕', '🔑', '📄', '💳', '⏳', '🎉'];
  var root = el(
    '<div id="sl-chat">' +
      '<div class="slc-feedback">Отзыв о сайте</div>' +
      '<button class="slc-launcher" type="button" aria-label="Открыть чат">' + (NEW ? I.bubble2 : I.bubble) + '</button>' +
      '<section class="slc-panel" role="dialog" aria-label="Чат с магазином">' +
        '<header class="slc-head">' +
          (NEW ? '<span class="slc-av slc-av--head">' + I.sofl + '</span>' : '<span class="slc-head__avatar">' + I.sofl + '</span>') +
          '<div class="slc-head__text"><div class="slc-head__name">' + BOT + '</div><div class="slc-head__role" hidden></div></div>' +
          '<button class="slc-head__btn" type="button" data-act="menu" aria-label="Меню">' + I.dots + '</button>' +
          '<button class="slc-head__btn" type="button" data-act="close" aria-label="Закрыть">' + I.close + '</button>' +
          '<nav class="slc-menu">' +
            '<button class="slc-menu__item" type="button" data-act="menu-item">' + I.mute + 'Отключить звук</button>' +
            '<button class="slc-menu__item" type="button" data-act="menu-item">' + I.mail + 'Отправить диалог на электронную почту</button>' +
            '<button class="slc-menu__item" type="button" data-act="menu-item">' + I.pen + 'Изменить личные данные</button>' +
          '</nav>' +
        '</header>' +
        '<div class="slc-body"></div>' +
        '<footer class="slc-foot">' +
          (NEW ? '<div class="slc-emoji" role="dialog" aria-label="Смайлики">' + EMOJI.map(function (e) { return '<button type="button" data-act="emoji-pick">' + e + '</button>'; }).join('') + '</div>' +
            '<label class="slc-input"><span class="slc-input__icon">' + I.clip + '</span><input type="text" placeholder="Напишите или запишите голосом" aria-label="Сообщение">' +
            '<button class="slc-input__icon slc-input__smile" type="button" data-act="emoji" aria-label="Смайлики">' + I.smile + '</button>' +
            '<button class="slc-input__send is-mic" type="button" data-act="send" aria-label="Записать голосом"><span class="slc-ic-mic">' + I.mic + '</span><span class="slc-ic-arrow">' + I.arrow + '</span></button></label>' +
            '<div class="slc-rec" aria-live="polite"><button class="slc-rec__cancel" type="button" data-act="rec-cancel" aria-label="Отменить запись">' + I.x + '</button><i class="slc-rec__dot"></i><span class="slc-rec__time">0:00</span><span class="slc-rec__text">Говорите, я слушаю</span>' +
            '<button class="slc-input__send" type="button" data-act="rec-send" aria-label="Отправить голосовое">' + I.arrow + '</button></div>' +
            '<div class="slc-credit"><span>Чат разработан</span>' + I.webim + '</div>'
          : '<div class="slc-emoji" role="dialog" aria-label="Смайлики">' + EMOJI.map(function (e) { return '<button type="button" data-act="emoji-pick">' + e + '</button>'; }).join('') + '</div>' +
            '<label class="slc-input"><span class="slc-input__icon">' + I.clip + '</span><input type="text" placeholder="Текст..." aria-label="Сообщение"><button class="slc-input__icon" type="button" data-act="emoji" aria-label="Смайлики">' + I.smile + '</button><button class="slc-input__icon" type="button" data-act="send" aria-label="Отправить">' + I.send + '</button></label>' +
            '<div class="slc-credit"><span>Чат разработан</span>' + I.webim + '</div>') +
        '</footer>' +
      '<div class="slc-survey" hidden><div class="slc-survey__sheet" role="dialog" aria-modal="true" aria-labelledby="slcSurveyQ">' +
        (NEW ? '<div class="slc-survey__head"><p class="slc-survey__q" id="slcSurveyQ">Оцените, помогли ли вам в чате?</p>' : '<div class="slc-survey__head"><b>Вопросы 1 из 1</b>') +
        '<button class="slc-survey__close" type="button" data-act="survey-close" aria-label="Закрыть оценку">' + I.xs + '</button></div>' +
        (NEW ? '' : '<p class="slc-survey__q" id="slcSurveyQ">Оцените, помогли ли вам в чате?</p>') +
        '<div class="slc-survey__stars" role="radiogroup" aria-label="Оценка от 1 до 5">' + [1, 2, 3, 4, 5].map(function (n) { return '<button type="button" role="radio" aria-checked="false" aria-label="' + n + ' из 5" data-act="star" data-n="' + n + '">' + I.star + '</button>'; }).join('') + '</div>' +
        (NEW ? '<p class="slc-survey__word" aria-live="polite"></p>' : '') +
        '<button class="slc-survey__send" type="button" data-act="survey-send"' + (NEW ? ' disabled>Отправить оценку' : '>Отправить') + '</button>' +
        '<div class="slc-credit"><span>Чат разработан</span>' + I.webim + '</div>' +
      '</div></div>' +
      '</section>' +
    '</div>');
  document.body.appendChild(root);

  var body = root.querySelector('.slc-body'), input = root.querySelector('input');
  var nameEl = root.querySelector('.slc-head__name'), roleEl = root.querySelector('.slc-head__role');
  var started = false, managerIn = false;
  var SCREEN = document.body.classList.contains('slc-screen');
  function hidePanel() { if (!SCREEN) root.classList.remove('is-open'); }

  function add(node) { body.appendChild(node); body.scrollTop = body.scrollHeight; return node; }
  function sys(text) { return add(el('<div class="slc-sys">' + esc(text) + '</div>')); }
  function bubbleMsg(inner, avatar, share) {
    if (NEW) return add(el('<div class="slc-msg">' + avHtml(avatar) + '<div class="slc-msg__col">' + inner + '</div></div>'));
    return add(el('<div class="slc-msg"><span class="slc-msg__avatar">' + avatar + '</span><div class="slc-msg__col">' + inner +
      '<div class="slc-time">' + hhmm() + '</div></div>' + (share ? '<span class="slc-share">' + I.share + '</span>' : '') + '</div>'));
  }
  // Бот Webim шлёт только простой текст, кнопки, файлы и перевод на оператора.
  // Карточки и **полужирный** остаются для шага 2 (свой виджет поверх Webim), их видно только по адресу с #cards
  var CARDS = NEW;
  // ссылки из ответа сервера (карточка товара, справка) открываются в новой вкладке
  function links(h) { return h.replace(/https?:\/\/[^\s<]*[^\s<.,;:!?)»]/g, function (u) { return '<a href="' + u + '" target="_blank" rel="noopener">' + u + '</a>'; }); }
  function rich(s) { return links(CARDS ? esc(ty(s)).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>') : esc(ty(s.replace(/\*\*/g, '')))); }
  function bot(text, avatar, share) { return bubbleMsg('<div class="slc-bubble">' + rich(text) + '</div>', avatar, share); }
  // карточка с главными цифрами внутри ответа агента (как message-card в Фигме)
  function cardHtml(c) {
    var h = '<div class="slc-bubble slc-bubble--card">' + (c.lead ? '<p class="slc-card__lead">' + rich(c.lead) + '</p>' : '') + '<div class="slc-card' + (c.grid ? ' slc-card--grid' : '') + '">';
    if (c.tag) h += '<span class="slc-card__tag">' + esc(c.tag) + '</span>';
    if (c.title) h += '<div class="slc-card__title">' + esc(ty(c.title)) + '</div>';
    if (c.meta) h += '<div class="slc-card__meta">' + esc(ty(c.meta)) + '</div>';
    (c.rows || []).forEach(function (r) { h += '<div class="slc-card__row' + (r[2] ? ' slc-card__row--strong' : '') + '"><span>' + esc(ty(r[0])) + '</span><b>' + esc(ty(r[1])) + '</b></div>'; });
    if (c.total) h += '<div class="slc-card__line"></div><div class="slc-card__row slc-card__row--strong"><span>' + esc(ty(c.total[0])) + '</span><b>' + esc(ty(c.total[1])) + '</b></div>';
    if (c.saving) h += '<div class="slc-card__saving">' + rich(c.saving) + '</div>';
    if (c.note) h += '<div class="slc-card__note">' + esc(ty(c.note)) + '</div>';
    return h + '</div>' + (c.tail ? '<p class="slc-card__tail">' + rich(c.tail) + '</p>' : '') + '</div>';
  }
  function me(text) {
    return add(el('<div class="slc-msg slc-msg--me"><div class="slc-msg__col"><div class="slc-bubble">' + esc(text) +
      '</div>' + (NEW ? '' : '<div class="slc-time">' + hhmm() + ' ' + I.checks + '</div>') + '</div></div>'));
  }
  // Голосовое сообщение клиента: волна, длительность и расшифровка под ней
  function meVoice(text, secs) {
    var wave = '', h = [6, 10, 14, 8, 16, 12, 6, 14, 18, 10, 8, 14, 12, 6, 10, 16, 8, 12, 6, 10, 14, 8];
    h.forEach(function (v) { wave += '<i style="height:' + v + 'px"></i>'; });
    return add(el('<div class="slc-msg slc-msg--me"><div class="slc-msg__col"><div class="slc-bubble slc-bubble--voice">' +
      '<div class="slc-voice"><span class="slc-voice__play">' + I.play + '</span><span class="slc-voice__wave">' + wave + '</span><span class="slc-voice__time">0:' + (secs < 10 ? '0' : '') + secs + '</span></div>' +
      '<div class="slc-voice__text">' + esc(ty(text)) + '</div></div></div></div>'));
  }

  function pills(list) {
    var box = el('<div class="slc-pills"></div>');
    list.forEach(function (p) {
      var b = el('<button class="slc-pill" type="button" data-act="pill">' + esc(p.text) + '</button>');
      b._go = p.go; box.appendChild(b);
    });
    return add(box);
  }

  /* ---------- Режим «как сейчас»: меню из шести тем, потом менеджер ---------- */
  function startNow() {
    bot('Здравствуйте! Чем вам помочь?', I.sofl, true);
    pills(TOPICS.map(function (t) { return { text: t, go: function () { sendNow(t); } }; }));
  }
  function callManagerNow() {
    if (managerIn) return; managerIn = true;
    setTimeout(function () {
      setHead(MANAGER.name, MANAGER.role);
      sys('Оператор ' + MANAGER.name + ' включился в разговор');
      bot('Здравствуйте! Чем я могу Вам помочь?', I.person, false);
    }, MANAGER_DELAY);
  }
  function sendNow(text) { me(text); callManagerNow(); }

  /* ---------- Режим «с агентом» ----------
     Агент пользуется только тем, что умеет бот Webim (External Bot API 2.0): текст, кнопки-ответы,
     файл по ссылке и перевод чата на оператора. Сводка для менеджера видна и клиенту.
     Особое условие менеджер решает в своём кабинете, и ответ клиенту приносит агент.
     В переписку менеджер входит сам, только когда нужен разговор: ошибка активации, вопрос без ответа в справке. */
  var st = { step: 'menu', cart: [], inn: '', invoice: '', topic: '', order: false };
  var queue = Promise.resolve();

  function setHead(name, role) {
    nameEl.textContent = name; roleEl.textContent = role; roleEl.hidden = !role;
    var av = root.querySelector('.slc-av--head');
    if (av) { av.innerHTML = name === MANAGER.name ? I.person : I.sofl; }
  }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  // «печатает»: агент отвечает за 1–2 секунды, как модель на стенде
  function say(text, opts) {
    opts = opts || {};
    queue = queue.then(function () {
      return wait(opts.pause || 0).then(function () {
        var dots = add(el('<div class="slc-msg slc-msg--typing">' + avHtml(opts.avatar || I.sofl) + '<div class="slc-msg__col"><div class="slc-bubble"><i></i><i></i><i></i></div></div></div>'));
        return wait(opts.delay || Math.min(1900, 700 + (text || '').length * 6)).then(function () {
          dots.remove();
          if (opts.card && CARDS) bubbleMsg(cardHtml(opts.card), opts.avatar || I.sofl, false);
          else if (text) bot(text, opts.avatar || I.sofl, false);
          if (opts.file) fileMsg(opts.file, opts.avatar);
          if (opts.pills) pills(opts.pills);
          if (opts.then) opts.then();
        });
      });
    });
    return queue;
  }
  // Разговор окончен: бот закрывает чат (close_chat в Умном боте 2.0), после закрытия Webim сам показывает опрос
  function closeChat() { queue = queue.then(function () { return wait(1500); }).then(function () { sys('Диалог завершён'); setTimeout(surveyOpen, 900); }); }
  function endWith(text) { return function () { st.step = 'ask'; say(text); closeChat(); }; }
  function fileMsg(f, avatar) {
    var m = bubbleMsg('<button class="slc-file" type="button" data-act="file"><span class="slc-file__icon">' + I.doc + '</span><span class="slc-file__text"><span class="slc-file__name">' + esc(f.name) +
      '</span><span class="slc-file__meta">' + (f.size ? 'PDF, ' + f.size + ' КБ' : 'PDF') + '</span></span></button>', avatar || I.sofl, false);
    var fb = m.querySelector('.slc-file'); fb._doc = f.doc; fb._url = f.url;
  }

  function workHours(d) { d = d || new Date(); if (/offhours/.test(location.hash)) return false; var w = d.getDay(), h = d.getHours(); return w >= 1 && w <= 5 && h >= 9 && h < 18; }
  function nextWorkDay() {
    var d = new Date(), n = 0;
    do { d.setDate(d.getDate() + 1); n++; } while (d.getDay() === 0 || d.getDay() === 6);
    return n === 1 ? 'завтра' : ['в воскресенье', 'в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу'][d.getDay()];
  }
  // срок ответа менеджера: на смене через 15 минут, вне смены следующим рабочим утром
  function deadline(sameDayText) { return workHours() ? sameDayText : nextWorkDay() + ' до 10:00'; }
  function sum(cart) { return cart.reduce(function (a, r) { return a + r.item.price * r.qty; }, 0); }
  function cartLine(cart) { return cart.map(function (r) { return r.item.short + ', ' + units(r.item, r.qty); }).join(' и '); }

  function startAgent() {
    setHead(BOT, AGENT_ROLE);
    say('Здравствуйте! Я ИИ-помощник магазина, отвечаю сразу по каталогу, заказам и счетам. Что не решу сам, передам менеджеру вместе с перепиской.\n\nВыберите тему или напишите вопрос.', {
      delay: 500,
      pills: [
        { text: TOPICS[0], go: topicInvoice },
        { text: TOPICS[1], go: topicTender },
        { text: TOPICS[2], go: topicDocs },
        { text: TOPICS[3], go: topicKeys },
        { text: TOPICS[4], go: function () { topicManager(TOPICS[4]); } },
        { text: TOPICS[5], go: topicAsk }
      ]
    });
  }

  function topicAsk() { st.step = 'ask'; say('Напишите вопрос своими словами.'); }
  function topicManager(topic) {
    st.step = 'describe'; st.topic = topic;
    say('Эту тему ведёт менеджер. Опишите задачу одним сообщением, я передам её вместе с перепиской, чтобы он не переспрашивал.');
  }
  function needInn(next, why) { if (st.inn) { next(); return; } st.step = 'inn'; st.afterInn = next; say(why || 'Напишите ИНН компании.'); }

  /* --- главный путь: продление Kaspersky --- */
  function answerRenew(q) {
    var r = CAT.kesRenew, n = CAT.kes;
    var text = 'Продление дешевле новой лицензии, но оформляется только на вашу прошлую лицензию Kaspersky.\n• продление: ' + money(r.price) + ' за узел на год;\n• новая: ' + money(n.price) + ' за узел на год.';
    if (q) text += '\n\nНа ' + units(r, q) + ': продление ' + money(r.price * q) + ', новая ' + money(n.price * q) + '.';
    text += '\n\nЦены из каталога на ' + ddmm() + '.';
    st.want = q;
    say(text, { card: {
      lead: 'Продление дешевле новой лицензии, но оформляется только на вашу прошлую лицензию Kaspersky.',
      title: q ? 'Цена на ' + units(r, q) + ', год' : 'Цена за узел на год',
      rows: q ? [['Продление', money(r.price * q), 1], ['Новая лицензия', money(n.price * q)]] : [['Продление', money(r.price), 1], ['Новая лицензия', money(n.price)]],
      note: (q ? money(r.price) + ' и ' + money(n.price) + ' за узел · ' : '') + 'каталог на ' + ddmm()
    } });
    needInn(renewFound, 'Проверю, подходит ли продление вам. **Напишите ИНН компании**.');
  }
  function renewFound() {
    st.order = true; st.step = 'renew';
    var q = ORDER.nodes, r = CAT.kesRenew, n = CAT.kes;
    st.cart = [{ item: r, qty: q }];
    var text = 'Нашёл вашу лицензию по заказу № ' + ORDER.no + ' от ' + ORDER.date + ': ' + ORDER.what + ', действует до ' + ORDER.until + '. Продление подходит.\n\nНа ' + units(r, q) + ': ' + money(r.price * q) + ' вместо ' + money(n.price * q) + ' за новую, экономия ' + money((n.price - r.price) * q) + '.';
    var extra = st.want && st.want > q ? st.want - q : 0;
    if (extra) { st.cart.push({ item: n, qty: extra }); text += '\n\nВ прошлой лицензии ' + units(r, q) + ', поэтому ещё ' + units(n, extra) + ' добавлю новой лицензией.'; }
    say(text, { card: {
      lead: 'Нашёл вашу лицензию по заказу № ' + ORDER.no + ', продление подходит.',
      title: ORDER.what.replace(/, 40\u00a0узлов$/, ''), meta: units(r, q) + ' · действует до ' + ORDER.until,
      total: ['Продление на год', money(r.price * q)],
      saving: 'Новая стоила бы ' + money(n.price * q) + ', **экономия ' + money((n.price - r.price) * q) + '**',
      tail: extra ? 'В прошлой лицензии ' + units(r, q) + ', поэтому ещё ' + units(n, extra) + ' добавлю новой лицензией.' : ''
    }, pills: [
      { text: 'КП: ' + cartLine(st.cart).replace(/Kaspersky Endpoint Security Стандартный, /g, ''), go: makeKp },
      { text: 'Добавить узлы', go: function () { st.step = 'add-nodes'; say('Сколько узлов добавить к ' + q + '?'); } }
    ] });
  }
  function makeKp() {
    st.step = 'after-kp';
    var until = plusDays(7);
    st.kpNo = 'КП-' + ddmm().replace('.', '') + '-' + st.cart[0].qty;
    var doc = docHtml('kp', until);
    say('КП на **' + money(sum(st.cart)) + '**, цена действует **до ' + dayMonth(until) + '**. Перешлите его руководителю или отправлю на почту. За два дня до конца срока напомню письмом.', {
      file: { name: 'КП продление Kaspersky, ' + units(CAT.kes, st.cart.reduce(function (a, r) { return a + r.qty; }, 0)) + '.pdf', size: 46, doc: doc },
      pills: [
        { text: 'Выставить счёт', go: function () { needInn(makeInvoice, 'Напишите ИНН компании, счёт выставлю на неё.'); } },
        { text: 'Отправить КП на почту', go: function () { st.step = 'mail'; st.mailWhat = 'КП'; say('На какую почту отправить?'); } }
      ]
    });
  }
  function makeInvoice(days) {
    st.step = 'after-invoice';
    var until = plusDays(days || 7);
    st.invoice = st.invoice || ddmm().replace('.', '') + '-0457';
    st.due = until;
    var doc = docHtml('invoice', until);
    var name = 'Счёт № ' + st.invoice + (days ? ', отсрочка ' + days + ' ' + plural(days, 'день', 'дня', 'дней') : '') + '.pdf';
    if (days) {
      say('Антон согласовал отсрочку на ' + days + ' ' + plural(days, 'день', 'дня', 'дней') + '. Новый счёт, оплатить до ' + dayMonth(until) + '. Ключ продления придёт на почту владельца заказа после оплаты.', { card: {
        lead: 'Антон согласовал отсрочку. Новый счёт ниже.', tag: 'Согласовано', grid: 1,
        rows: [['Отсрочка', days + ' ' + plural(days, 'день', 'дня', 'дней')], ['Оплатить до', dayMonth(until)], ['Сумма', money(sum(st.cart))]],
        tail: 'Ключ продления придёт на почту владельца заказа после оплаты.'
      }, file: { name: name, size: 52, doc: doc }, pause: 4500,
        pills: [{ text: 'Спасибо, всё понятно', go: endWith('Хорошо. Если появятся вопросы по заказу, пишите сюда.') }] });
      return;
    }
    say('Счёт на **' + money(sum(st.cart)) + '** для ИНН ' + st.inn + ' готов. Оплатите **до ' + dayMonth(until) + '**, до этой даты цена не изменится. Ключ продления придёт на почту владельца заказа после оплаты.', {
      file: { name: name, size: 52, doc: doc },
      pills: [
        { text: 'Нужна отсрочка платежа', go: askDelay },
        { text: 'Спасибо, всё понятно', go: endWith('Хорошо. Если появятся вопросы по заказу, пишите сюда.') }
      ]
    });
  }
  function askDelay() {
    st.step = 'delay';
    say('На сколько дней нужна отсрочка?', { pills: [14, 30, 45].map(function (d) { return { text: d + ' дней', go: function () { delayAsked(d); } }; }) });
  }
  // особое условие: решает менеджер в кабинете, агент приносит ответ сюда
  function delayAsked(days) {
    st.step = 'wait-manager';
    var on = workHours();
    say('Отсрочку решает менеджер, у меня на неё нет правила. Передал Антону сводку:\n• ' + cartLine(st.cart) + ', ' + money(sum(st.cart)) + '\n• счёт № ' + st.invoice + ', ИНН ' + st.inn + '\n• просьба: отсрочка ' + days + ' дней\n\n' +
      (on ? 'Антон на смене, ответ придёт сюда в течение 15 минут.' : 'Менеджеры работают по будням с 9:00 до 18:00. Антон ответит ' + deadline() + ', решение придёт сюда и на почту владельца заказа.') + ' Писать заново ничего не нужно.',
      { card: {
        lead: 'Отсрочку решает менеджер, у меня на неё нет правила. Передал Антону сводку:', grid: 1,
        rows: [['Товар', cartLine(st.cart)], ['Счёт', '№ ' + st.invoice + ' на ' + money(sum(st.cart))], ['Просьба', 'отсрочка ' + days + ' дней']],
        tail: (on ? 'Антон на смене, ответ придёт сюда **в течение 15 минут**.' : 'Менеджеры работают по будням с 9:00 до 18:00. Антон ответит **' + deadline() + '**, решение придёт сюда и на почту владельца заказа.') + ' Писать заново ничего не нужно.'
      }, then: function () { if (on) makeInvoice(days); } });
  }

  /* --- короткий случай 1: УПД для бухгалтерии --- */
  function topicDocs() { st.topic = 'docs'; needInn(docsFound, 'Напишите номер заказа или ИНН компании.'); }
  function docsFound() {
    st.order = true; st.step = 'after-docs';
    say('Заказ № ' + ORDER.no + ' от ' + ORDER.date + ' **выполнен**: ' + ORDER.what + '. Закрывающий документ: **УПД № ' + ORDER.no + ' от ' + ORDER.date + '**.', {
      file: { name: 'УПД № ' + ORDER.no + '.pdf', size: 38, doc: docHtml('upd') },
      pills: [
        { text: 'Отправить в бухгалтерию', go: function () { st.step = 'mail'; st.mailWhat = 'УПД'; say('На какую почту отправить?'); } },
        { text: 'Спасибо', go: endWith('Хорошо. Если понадобятся другие документы, пишите сюда.') }
      ]
    });
  }

  /* --- короткий случай 2: госзакупка --- */
  function topicTender() {
    st.step = 'tender'; st.topic = TOPICS[1];
    say('Для госзакупки соберу КП для обоснования цены. Напишите товары и количество, например: Astra Linux для рабочей станции, 40 лицензий.');
  }
  function tenderKp(item, q) {
    st.step = 'wait-manager';
    st.cart = [{ item: item, qty: q }];
    st.kpNo = 'КП-' + ddmm().replace('.', '') + '-Г' + q;
    var h = new Date().getHours(), by = workHours() ? 'сегодня до ' + Math.min(18, h + 2) + ':00' : deadline();
    say('Собрал черновик КП: ' + cartLine(st.cart) + ', **' + money(sum(st.cart)) + '**. Для закупки КП нужно с подписью, её ставит менеджер. Передал Антону, подписанное КП придёт сюда и на почту ' + by + '.', {
      file: { name: 'КП для обоснования цены, черновик.pdf', size: 44, doc: docHtml('tender', plusDays(30)) }
    });
  }

  /* --- ключи --- */
  function topicKeys() { st.topic = 'keys'; needInn(keysFound, 'Напишите номер заказа или ИНН компании. Найду заказ и проверю ключи.'); }
  function keysFound() {
    st.order = true; st.step = 'after-keys';
    st.ref = RENEW;
    say('По заказу № ' + RENEW.no + ' ключ продления ушёл ' + RENEW.sent + ' на почту владельца заказа ' + ORDER.mail + '. **Отправил его ещё раз**, письмо придёт **в течение 5 минут**. Если его нет во входящих, проверьте папку «Спам».', {
      pills: [
        { text: 'Письмо пришло', go: function () { st.step = 'ask'; say('Хорошо. Если при активации появится ошибка, пришлите её текст или снимок экрана, разберу.'); } },
        { text: 'Письмо не пришло', go: function () { handoff('ключ не пришёл после повторной отправки'); } },
        { text: 'Ключ не активируется', go: function () { handoff('ключ не активируется'); } }
      ]
    });
  }

  // Нужен разговор с человеком: агент переводит чат на менеджера со сводкой, менеджер входит в переписку
  function handoff(ask, label) {
    st.step = 'manager';
    var lines = [], rows = [];
    if (st.order) { var ref = st.ref || ORDER; lines.push('заказ № ' + ref.no + ', ' + ref.what); rows.push(['Заказ', '№ ' + ref.no + ', ' + ref.what]); }
    if (st.inn) { lines.push('ИНН ' + st.inn); rows.push(['ИНН', st.inn]); }
    if (st.topic && /^[А-Я]/.test(st.topic)) { lines.push('тема: ' + st.topic); rows.push(['Тема', st.topic]); }
    lines.push((label || 'просьба') + ': ' + ask);
    rows.push([(label || 'просьба').replace(/^./, function (c) { return c.toUpperCase(); }), ask]);
    var on = workHours();
    var when = on ? 'Менеджер подключится здесь, обычно за 5 минут. Повторять ничего не нужно.'
      : 'Менеджеры работают по будням с 9:00 до 18:00. Ответят ' + deadline() + ' здесь в чате. Повторять ничего не нужно.';
    say('Это решит менеджер. Передал ему сводку:\n• ' + lines.join('\n• ') + '\n\n' + when, { card: {
      lead: 'Это решит менеджер. Передал ему сводку:', grid: 1, rows: rows,
      tail: when.replace(/обычно за 5 минут/, '**обычно за 5 минут**')
    }, then: function () { if (on) managerJoins(ask); } });
  }
  function managerJoins(ask) {
    setTimeout(function () {
      managerIn = true;
      setHead(MANAGER.name, MANAGER.role);
      sys(MANAGER.name + ' подключился к чату');
      var first = /не пришёл/.test(ask) ? 'Здравствуйте! Сводку по заказу вижу. Проверю отправку и пришлю ключ сюда в чат в течение 15 минут.'
        : /активир/.test(ask) ? 'Здравствуйте! Сводку по заказу вижу. Напишите, пожалуйста, какую ошибку показывает программа при активации.'
        : 'Здравствуйте! Сводку вижу, переспрашивать не буду. Сейчас посмотрю и отвечу здесь.';
      say(first, { avatar: I.person, delay: 1400 });
    }, MANAGER_DELAY);
  }
  function managerReply() { say('Понял, отвечу здесь в течение часа.', { avatar: I.person, delay: 1800 }); }

  function findItem(t) {
    if (/касперск|kaspersky|endpoint|антивирус/i.test(t)) return 'kes';
    if (/astra|астр/i.test(t)) return CAT.astra;
    if (/крипто|crypto|csp/i.test(t)) return 'cp';
    return null;
  }
  function findQty(t) {
    var m = t.replace(/\d{9,}/g, '').replace(/\d+\s*-?\s*фз/gi, '').match(/(\d{1,4})\s*(мест|раб|лиц|шт|пк|комп|узл|устр|сотр|польз|ключ)?/i);
    return m ? parseInt(m[1], 10) : 0;
  }
  function answerCrypto(q) {
    var y = CAT.cpYear, p = CAT.cpPerm;
    var text = 'КриптоПро CSP 5.0 на одно рабочее место:\n• годовая: ' + money(y.price) + ' на 1 год;\n• бессрочная: ' + money(p.price) + ', платите один раз.';
    if (q) text += '\n\nНа ' + units(y, q) + ' годовая стоит ' + money(y.price * q) + ' каждый год, бессрочная ' + money(p.price * q) + ' один раз.';
    text += '\n\nБессрочная окупается за два года, дальше она выгоднее. Цены из каталога на ' + ddmm() + '.';
    st.step = 'ask';
    say(text);
  }

  function onText(t) {
    var digits = t.replace(/[\s-]/g, '');
    if (st.step === 'manager') { if (managerIn) managerReply(t); return; }
    if (st.step === 'wait-manager') { say('Передал это Антону вместе со сводкой.'); return; }
    if (st.step === 'inn') {
      if (/^\d+$/.test(digits) && (digits.length === 10 || digits.length === 12)) { st.inn = digits; st.step = ''; st.afterInn(); return; }
      if (/^\d{3,9}$/.test(digits) && st.topic !== '') { st.step = ''; st.afterInn(); return; } // номер заказа
      say('ИНН состоит из 10 или 12 цифр. Проверьте, пожалуйста, и пришлите ещё раз.'); return;
    }
    if (st.step === 'add-nodes') { var a = findQty(t); if (!a) { say('Напишите число, например 5.'); return; } st.cart = [{ item: CAT.kesRenew, qty: ORDER.nodes }, { item: CAT.kes, qty: a }]; makeKp(); return; }
    if (st.step === 'mail') {
      if (!/@/.test(t)) { say('Пришлите адрес почты, например buh@company.ru.'); return; }
      st.step = 'ask'; say('Отправил ' + st.mailWhat + ' на ' + t.trim() + '.'); return;
    }
    if (st.step === 'delay') { var d = findQty(t); if (d) { delayAsked(d); return; } }
    if (st.step === 'describe') { handoff(short(t), 'задача'); return; }
    var item = findItem(t), q = findQty(t);
    if (st.step === 'tender' || /госзакуп|тендер|44\s*-?\s*фз|223\s*-?\s*фз|нмцк/i.test(t)) {
      var ti = item && typeof item === 'object' ? item : item === 'kes' ? CAT.kes : null;
      if (ti && q) { tenderKp(ti, q); return; }
      if (st.step !== 'tender') { topicTender(); return; }
      say('Напишите товар и количество, например: Astra Linux, 40 лицензий.'); return;
    }
    if (/отсрочк|рассрочк|постоплат|в долг/i.test(t)) { if (st.invoice) askDelay(); else handoff('отсрочка платежа'); return; }
    if (/упд|закрывающ|акт|сч[её]т-фактур|документ/i.test(t)) { topicDocs(); return; }
    if (/ключ|активац/i.test(t) && !item) { topicKeys(); return; }
    if (item === 'kes') { answerRenew(q); return; }
    if (item === 'cp' && /бессроч|годов|подписк|лиценз|(^|[^а-яё])(цен|стои|сколько|куп|брать|взять)/i.test(t)) { answerCrypto(q); return; }
    if (/продл/i.test(t)) { answerRenew(q); return; }
    if (/сч[её]т/i.test(t)) { topicInvoice(); return; }
    // нет ответа в справке и каталоге: не выдумывает, а передаёт
    say('В справке и каталоге нет точного ответа на этот вопрос, гадать не буду.', { delay: 1100 });
    handoff(short(t), 'вопрос');
  }
  function short(t) { return '«' + (t.length > 90 ? t.slice(0, 88) + '…' : t) + '»'; }
  function topicInvoice() {
    if (st.cart.length) { needInn(makeInvoice, 'Напишите ИНН компании, счёт выставлю на неё.'); return; }
    st.step = 'ask';
    say('Что включить в счёт? Напишите товар и количество, например: продление Kaspersky на 40 узлов.');
  }

  /* ---------- КП и счёт: документ открывается в новой вкладке ---------- */
  function docHtml(kind, until) {
    var today = new Date(), cart = st.cart, rows = '', total = sum(cart), who = '', note = '';
    var title = { kp: 'Коммерческое предложение № ' + st.kpNo, invoice: 'Счёт на оплату № ' + st.invoice, upd: 'Универсальный передаточный документ № ' + ORDER.no, tender: 'Коммерческое предложение № ' + st.kpNo }[kind];
    if (kind === 'upd') { cart = [{ item: { name: 'Kaspersky Endpoint Security для бизнеса Стандартный, лицензия на 1 год, 1 узел' }, qty: ORDER.nodes }]; }
    cart.forEach(function (r, i) {
      rows += '<tr><td>' + (i + 1) + '</td><td>' + esc(r.item.name) + '</td><td class="r">' + r.qty + '</td>' +
        (kind === 'upd' ? '<td></td><td></td>' : '<td class="r">' + money(r.item.price) + '</td><td class="r">' + money(r.item.price * r.qty) + '</td>') + '</tr>';
    });
    if (kind === 'invoice' || kind === 'upd') who = '<p class="m">Покупатель: ИНН ' + esc(st.inn || '—') + '</p>';
    if (kind === 'kp') note = 'Цена действует до ' + dayMonth(until) + ' ' + until.getFullYear() + ' года. Продление оформляется на лицензию из заказа № ' + ORDER.no + '.';
    if (kind === 'invoice') note = 'Оплатить до ' + dayMonth(until) + ' ' + until.getFullYear() + ' года. Ключ придёт на почту владельца заказа после оплаты.';
    if (kind === 'tender') note = 'Для обоснования начальной цены контракта. Цена действует до ' + dayMonth(until) + ' ' + until.getFullYear() + ' года. Черновик: подпись ставит менеджер.';
    var day = kind === 'upd' ? ORDER.date : dayMonth(today) + ' ' + today.getFullYear() + ' года';
    return '<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>' + esc(title) + '</title><style>' +
      'body{margin:0;background:#eef0f4;font:14px/1.5 Arial,sans-serif;color:#222}.p{width:794px;min-height:1000px;margin:24px auto;background:#fff;padding:56px 64px;box-sizing:border-box}' +
      '.b{color:#c60b46;font-weight:700;font-size:18px;margin:0 0 40px}h1{font-size:22px;margin:0 0 4px}.m{margin:0;color:#555}' +
      'table{width:100%;border-collapse:collapse;margin:32px 0 16px}th,td{padding:10px 8px;border-bottom:1px solid #dde0e8;text-align:left;vertical-align:top}th{font-weight:400;color:#777;font-size:12px}' +
      '.r{text-align:right;white-space:nowrap}.t{display:flex;justify-content:flex-end;gap:24px;font-size:18px;font-weight:700;margin:0 0 32px}.f{margin-top:64px;color:#999;font-size:12px}</style></head><body><div class="p">' +
      '<p class="b">Softline Store</p><h1>' + esc(title) + '</h1><p class="m">от ' + day + '</p>' + who +
      '<table><tr><th>№</th><th>Товар</th><th class="r">Кол-во</th><th class="r">Цена</th><th class="r">Сумма</th></tr>' + rows + '</table>' +
      (kind === 'upd' ? '' : '<div class="t"><span>Итого</span><span>' + money(total) + '</span></div>') + (note ? '<p>' + esc(note) + '</p>' : '') +
      '<p class="f">Образец документа для демонстрации. Подготовил ИИ-помощник Softline Store по данным магазина.</p></div></body></html>';
  }
  function openDoc(html) { var u = URL.createObjectURL(new Blob([html], { type: 'text/html' })); window.open(u, '_blank'); }

  /* ---------- Живой режим: агент на сервере ----------
     Интерфейс только показывает то, что прислал сервер: текст, кнопки-ответы, файлы, серые строки и закрытие.
     Ключей и логики агента здесь нет. Форма сообщений как у бота Webim, перевод в api.js. */
  var live = (function () {
    var sid = '', lastSeq = 0, timer = 0, closed = false, busy = 0, dots = null;
    var KEY = 'sl-support-session';
    function call(method, path, body) {
      // живой API: запросы переводит api.js, экран остаётся тем же
      if (window.SupportBackend) return window.SupportBackend.call(method, path, body);
      var ctl = window.AbortController ? new AbortController() : null;
      var t = ctl ? setTimeout(function () { ctl.abort(); }, 60000) : 0;
      return fetch(API + path, {
        method: method, credentials: 'same-origin', signal: ctl ? ctl.signal : undefined,
        headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined
      }).then(function (r) {
        clearTimeout(t);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.status === 204 ? {} : r.json();
      }, function (e) { clearTimeout(t); throw e; });
    }
    function typing(on) {
      if (on && !dots) dots = add(el('<div class="slc-msg slc-msg--typing">' + avHtml(I.sofl) + '<div class="slc-msg__col"><div class="slc-bubble"><i></i><i></i><i></i></div></div></div>'));
      if (!on && dots) { dots.remove(); dots = null; }
      if (on && dots) body.appendChild(dots);
    }
    // all: показать и реплики клиента (после перезагрузки страницы); в обычном ходе они уже на экране
    function show(list, all) {
      (list || []).forEach(function (m) {
        if (m.seq != null) { if (m.seq <= lastSeq) return; lastSeq = m.seq; }
        var t = m.type || 'text';
        if (m.from === 'client') { if (m.text && all) me(m.text); return; }
        if (m.from === 'system') { if (m.text) sys(m.text); return; }
        var av = m.from === 'manager' ? I.person : I.sofl;
        if (m.from === 'manager' && m.author && nameEl.textContent !== m.author) setHead(m.author, MANAGER.role);
        if (t === 'close') { closed = true; stop(); if (m.text) bot(m.text, av, false); sys('Диалог завершён'); setTimeout(surveyOpen, 900); return; }
        if (m.text) bot(m.text, av, false);
        if (t === 'file' && m.file) fileMsg({ name: m.file.name, size: m.file.size_kb, url: m.file.url }, av);
        if (m.buttons && m.buttons.length) {
          var box = pills(m.buttons.map(function (b) { return { text: b.text }; }));
          [].forEach.call(box.children, function (b, i) { b._live = m.buttons[i].id || m.buttons[i].text; });
        }
      });
      if (dots) body.appendChild(dots);
      body.scrollTop = body.scrollHeight;
    }
    function poll() {
      if (!sid || closed || busy) return;
      call('GET', '/chat/sessions/' + encodeURIComponent(sid) + '/messages?after=' + lastSeq).then(function (r) {
        if (!busy) show(r.messages);
      }, function () {});
    }
    function run() { stop(); timer = setInterval(poll, 3000); }
    function stop() { clearInterval(timer); timer = 0; }
    // Сервер не ответил: говорим прямо и даём написать ещё раз, следующее сообщение снова пойдёт на сервер
    function fail() {
      typing(false);
      sys('Помощник сейчас не отвечает. Напишите ещё раз через минуту');
    }
    function open() {
      return call('POST', '/chat/sessions', { page: location.href }).then(function (r) {
        sid = r.session_id || ''; try { sessionStorage.setItem(KEY, sid); } catch (e) {}
        show(r.messages); run();
      });
    }
    function fresh() {
      sys('Сегодня, ' + hhmm()); typing(true);
      open().then(function () { typing(false); }, fail);
    }
    function start() {
      setHead(BOT, AGENT_ROLE);
      var saved = ''; try { saved = sessionStorage.getItem(KEY) || ''; } catch (e) {}
      if (!saved) { fresh(); return; }
      // перезагрузили страницу: тот же разговор целиком
      sid = saved; typing(true);
      call('GET', '/chat/sessions/' + encodeURIComponent(sid) + '/messages?after=0').then(function (r) {
        typing(false); show(r.messages, true); if (!closed) run();
      }, function () { sid = ''; try { sessionStorage.removeItem(KEY); } catch (e) {} typing(false); fresh(); });
    }
    function send(text, buttonId, echoed) {
      text = String(text || '').trim(); if (!text) return;
      // ответ клиента закрывает прежние кнопки-ответы: живы только кнопки последней реплики, как после перезагрузки
      [].forEach.call(body.querySelectorAll('.slc-pills'), function (x) { x.remove(); });
      if (!echoed) me(text);
      busy++; typing(true);
      var data = { text: text }; if (buttonId) data.button_id = buttonId;
      (sid ? Promise.resolve() : open()).then(function () {
        return call('POST', '/chat/sessions/' + encodeURIComponent(sid) + '/messages', data);
      }).then(function (r) {
        busy--; typing(false); show(r.messages);
      }, function () { busy--; fail(); });
    }
    function rate(n) { if (sid) call('POST', '/chat/sessions/' + encodeURIComponent(sid) + '/rating', { stars: n }).catch(function () {}); }
    return { start: start, send: send, rate: rate };
  })();

  /* ---------- общее ---------- */
  function start() {
    if (started) return; started = true;
    if (MODE === 'now') { add(el('<div class="slc-date">' + ddmm() + '</div>')); sys('Оператор ' + BOT + ' включился в разговор'); startNow(); }
    else if (LIVE) live.start();
    else { sys('Сегодня, ' + hhmm()); startAgent(); }
  }
  function send(text) {
    text = (text || '').trim(); if (!text) return;
    if (LIVE) { live.send(text); return; }
    me(text);
    if (MODE === 'now') { if (managerIn && /спасиб/i.test(text)) { bot('Рад был помочь! Хорошего дня.', I.person, false); closeChat(); } else callManagerNow(); }
    else onText(text);
  }

  /* ---------- Оценка чата: как опрос Webim, выскакивает при закрытии после разговора ---------- */
  var survey = root.querySelector('.slc-survey'), rating = 0, surveyDone = false;
  var WORDS = ['', 'Плохо', 'Так себе', 'Нормально', 'Хорошо', 'Отлично'];
  function surveyOpen() { if (surveyDone) return; survey.hidden = false; requestAnimationFrame(function () { survey.classList.add('is-open'); }); }
  function surveyHide() { survey.classList.remove('is-open'); survey.hidden = true; }
  function surveyRate(n) {
    rating = n;
    survey.querySelectorAll('[data-act="star"]').forEach(function (s, i) { s.classList.toggle('is-on', i < n); s.setAttribute('aria-checked', i === n - 1 ? 'true' : 'false'); });
    var w = survey.querySelector('.slc-survey__word');
    // низкая оценка уходит менеджеру в «На проверку», клиенту говорим об этом прямо
    if (w) w.textContent = n <= 3 ? WORDS[n] + '. Разговор посмотрит менеджер' : WORDS[n];
    var send = survey.querySelector('.slc-survey__send'); send.disabled = false;
  }
  function surveyThanks() {
    var sh = survey.querySelector('.slc-survey__sheet');
    sh.innerHTML = '<p class="slc-survey__thanks">Спасибо за оценку</p>';
    setTimeout(function () { hidePanel(); setTimeout(surveyHide, 250); }, 1400);
  }

  root.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act], .slc-launcher'); if (!b) return;
    if (b.classList.contains('slc-launcher')) { root.classList.add('is-open'); start(); setTimeout(function () { input.focus(); }, 200); return; }
    var act = b.getAttribute('data-act');
    var menu = root.querySelector('.slc-menu');
    if (act === 'close') { hidePanel(); menu.classList.remove('is-open'); }
    else if (act === 'survey-close') { surveyDone = true; surveyHide(); hidePanel(); }
    else if (act === 'star') surveyRate(+b.getAttribute('data-n'));
    else if (act === 'survey-send') { if (!rating) return; surveyDone = true; if (LIVE) live.rate(rating); surveyThanks(); }
    else if (act === 'menu') menu.classList.toggle('is-open');
    else if (act === 'menu-item') menu.classList.remove('is-open');
    else if (act === 'pill') {
      var box = b.parentNode; if (box.classList.contains('is-used')) return;
      box.classList.add('is-used'); b.classList.add('is-on');
      if (NEW) box.remove(); // кнопки пропадают, выбор становится сообщением клиента
      me(b.textContent);
      if (MODE === 'now') callManagerNow(); else if (b._live) live.send(b.textContent, b._live, true); else b._go();
    }
    else if (act === 'file') { if (b._url) window.open(b._url, '_blank', 'noopener'); else openDoc(b._doc); }
    else if (act === 'send') { if (NEW && !input.value.trim()) recStart(); else { send(input.value); input.value = ''; sendState(); } }
    else if (act === 'emoji') root.querySelector('.slc-emoji').classList.toggle('is-open');
    else if (act === 'emoji-pick') { var pos = input.selectionStart == null ? input.value.length : input.selectionStart; input.value = input.value.slice(0, pos) + b.textContent + input.value.slice(pos); root.querySelector('.slc-emoji').classList.remove('is-open'); input.focus(); sendState(); }
    else if (act === 'rec-cancel') recStop(false);
    else if (act === 'rec-send') recStop(true);
  });
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { send(input.value); input.value = ''; sendState(); } });

  /* ---------- Голосом: запись, расшифровка в браузере, ответ по тексту ---------- */
  // Круглая кнопка: пустое поле = микрофон, есть текст = отправить
  var sendBtn = root.querySelector('.slc-input .slc-input__send');
  function sendState() { if (!NEW) return; var t = !!input.value.trim(); sendBtn.classList.toggle('is-mic', !t); sendBtn.setAttribute('aria-label', t ? 'Отправить' : 'Записать голосом'); }
  input.addEventListener('input', sendState);
  // На демо без интернета или без доступа к микрофону расшифровка подставляется из сценария
  var VOICE_DEMO = 'У нас Касперский на 40 компьютеров заканчивается в декабре. Брать продление или новую?';
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var rec = null, recT0 = 0, recTimer = 0, recText = '', recSend = false, recDone = false;
  var foot = root.querySelector('.slc-foot');
  function recShow(t) { var n = root.querySelector('.slc-rec__text'); if (n) n.textContent = t; }
  function recStart() {
    if (!NEW || foot.classList.contains('is-rec')) return;
    foot.classList.add('is-rec'); recT0 = Date.now(); recText = ''; recSend = false; recDone = false; recShow('Говорите, я слушаю');
    var tEl = root.querySelector('.slc-rec__time'); tEl.textContent = '0:00';
    recTimer = setInterval(function () { var s = Math.floor((Date.now() - recT0) / 1000); tEl.textContent = Math.floor(s / 60) + ':' + (s % 60 < 10 ? '0' : '') + (s % 60); }, 250);
    if (!SR) return;
    try {
      rec = new SR(); rec.lang = 'ru-RU'; rec.interimResults = true; rec.continuous = true;
      rec.onresult = function (e) { var fin = '', tmp = ''; for (var i = 0; i < e.results.length; i++) { if (e.results[i].isFinal) fin += e.results[i][0].transcript; else tmp += e.results[i][0].transcript; } recText = (fin + ' ' + tmp).trim(); if (recText) recShow(recText); };
      rec.onerror = function () { rec = null; };
      rec.onend = function () { if (recSend) recFinish(); };
      rec.start();
    } catch (err) { rec = null; }
  }
  function recStop(sendIt) {
    clearInterval(recTimer); recSend = sendIt;
    if (rec) { try { rec.stop(); } catch (err) {} setTimeout(function () { if (recSend) recFinish(); }, 1500); }
    else if (sendIt) recFinish();
    if (!sendIt) { foot.classList.remove('is-rec'); rec = null; }
  }
  function recFinish() {
    if (recDone) return; recDone = true; rec = null;
    foot.classList.remove('is-rec');
    var secs = Math.max(1, Math.min(59, Math.round((Date.now() - recT0) / 1000)));
    var text = recText.trim() ? recText.trim().replace(/^./, function (c) { return c.toUpperCase(); }) : VOICE_DEMO;
    meVoice(text, secs);
    onText(text);
  }
  window.addEventListener('hashchange', function () { location.reload(); });

  // Свой экран чата (index.html, класс slc-screen у body): окно открыто сразу и не прячется после оценки
  if (SCREEN) { root.classList.add('is-open'); start(); if (matchMedia('(min-width: 761px)').matches) input.focus(); }

})();
