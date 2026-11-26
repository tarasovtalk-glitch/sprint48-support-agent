// Тестовые обращения для просмотра кабинета жюри (/support/cabinet/?jury).
//
//   SUPPORT_DEMO_KEY=… SUPPORT_MANAGER_KEY=… node scripts/jury-cases.mjs http://127.0.0.1:8000/support/api > src/cabinet/jury-cases.json
//
// Скрипт проходит в чате стенда шесть тестовых разговоров с тестовыми реквизитами, которые сервер сам подсказывает
// (ООО «Демо», ИНН 0000000000, КПП 000000000), по двум принимает решение как менеджер и сохраняет из журнала
// только эти разговоры: строки GET /manager/cases?state=all и журнал каждого (GET /manager/cases/{id}/journal).
// Просмотр для жюри читает этот файл и никуда не пишет, ключ менеджера жюри не нужен.
//
// Запускать на сервере против внутреннего адреса API: там действует X-Demo-Key и нет ограничения открытого стенда
// (10 запросов в минуту с адреса). Ход разговоров печатается в stderr, файл с журналом идёт в stdout.
import { randomUUID } from 'node:crypto';

const API = String(process.argv[2] || 'http://127.0.0.1:8000/support/api').replace(/\/$/, '');
const DEMO_KEY = process.env.SUPPORT_DEMO_KEY || '';
const MANAGER_KEY = process.env.SUPPORT_MANAGER_KEY || '';
const REQUISITES = 'ООО «Демо», ИНН 0000000000, КПП 000000000';

// реплика клиента: text, или кнопка последнего ответа агента по подписи (press) или по действию (action)
const CASES = [
  { name: 'КП ждёт проверки', steps: [
    { text: 'Добрый день. Нужно коммерческое предложение на 19 бессрочных лицензий КриптоПро CSP' },
    { press: /рабочие места/i },
    { text: REQUISITES }] },
  { name: 'КП согласовано менеджером', steps: [
    { text: 'Нужно защитить почту и файлы на 50 сотрудников' },
    { press: /почта, и файлы/i }, { press: /12 месяцев/i }, { press: /свои серверы/i },
    { action: 'select_offer' }, { text: REQUISITES }], manager: { choice: 'approve' } },
  { name: 'Скидка больше 5%', steps: [
    { text: 'Здравствуйте, нужен MDaemon на 10 пользователей. Можно оплатить с отсрочкой?' },
    { text: 'А больше скидку можно? Хотя бы 10%' }] },
  { name: 'Госзакупка, ответил менеджер', steps: [
    { text: 'Мы проводим госзакупку на антивирус, нужен менеджер' }],
    manager: { choice: 'approve', reply: 'Здравствуйте! Пришлите номер закупки, подготовлю КП по её условиям и отвечу здесь.' } },
  { name: 'Закрывающие документы', steps: [
    { text: 'Где закрывающие документы по заказу?' }] },
  { name: 'Цена по каталогу и вопрос про реестр', steps: [
    { text: 'MDaemon на 10 пользователей, сколько стоит?' },
    { press: /12 месяцев/i }, { press: /свои серверы/i },
    { text: 'а есть российский аналог?' }] }
];

const log = (...a) => console.error(...a);
// журнал пишет время с точностью до секунды: пауза между репликами, чтобы шаги агента встали под свою реплику
const pause = () => new Promise(r => setTimeout(r, 1100));
async function api(method, path, body, headers = {}) {
  const r = await fetch(API + path, {
    method, headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...headers }, body: body ? JSON.stringify(body) : undefined
  });
  if (!r.ok) throw new Error(method + ' ' + path + ': HTTP ' + r.status + ' ' + (await r.text()).slice(0, 200));
  return r.status === 204 ? {} : r.json();
}
const manager = (method, path, body) => api(method, path, body, { 'X-Manager-Key': MANAGER_KEY });

async function play(c) {
  const s = await api('POST', '/sessions', null, DEMO_KEY ? { 'X-Demo-Key': DEMO_KEY } : {});
  const auth = { Authorization: 'Bearer ' + s.session_token };
  let buttons = [];
  log('\n== ' + c.name);
  for (const step of c.steps) {
    let body;
    if (step.text) body = { text: step.text };
    else {
      const b = buttons.find(x => step.press ? step.press.test(x.label) : x.action === step.action);
      if (!b) { log('  нет кнопки', step.press || step.action, 'среди', buttons.map(x => x.label).join(' | ')); break; }
      body = { action: b.action, value: b.value || '' };
    }
    await pause();
    const r = await api('POST', '/case/messages', body, auth);
    log('  клиент:', step.text || '[' + (step.press || step.action) + ']');
    log('  агент:', String(r.reply || '').replace(/\s+/g, ' ').slice(0, 160), (r.buttons || []).length ? '{' + r.buttons.map(x => x.label).join(' | ') + '}' : '');
    buttons = r.buttons || [];
  }
  if (c.manager) {
    await pause();
    const row = ((await manager('GET', '/manager/cases')).cases || []).find(x => x.id === s.case.id);
    if (!row) log('  менеджер: разговора нет в очереди');
    else {
      const body = { choice: c.manager.choice, version: row.version, request_id: randomUUID() };
      if (c.manager.reply) body.reply = c.manager.reply;
      const v = await manager('POST', '/manager/cases/' + s.case.id + '/decision', body);
      log('  менеджер:', c.manager.choice, '→', v.state);
    }
  }
  return s.case.id;
}

const ids = [];
for (const c of CASES) ids.push(await play(c));
const all = (await manager('GET', '/manager/cases?state=all&limit=50&offset=0')).cases || [];
const cases = all.filter(x => ids.includes(x.id));
const journal = {};
for (const id of ids) {
  const j = await manager('GET', '/manager/cases/' + id + '/journal');
  // ссылка на PDF живёт 15 минут: в просмотре файла нет, остаётся только отметка, что он был
  (j.messages || []).forEach(m => { if (m.document_url) m.document_url = 'expired'; });
  journal[id] = j;
}
log('\nразговоров в файле:', cases.length, 'из', ids.length);
process.stdout.write(JSON.stringify({ taken: new Date().toISOString(), cases, journal }, null, 1) + '\n');
