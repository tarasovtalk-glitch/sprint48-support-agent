// Заглушка API для локальной проверки интерфейса (npm start). Это не агент:
// ответы по ключевым словам, данные в памяти, после перезапуска всё сначала.
// Настоящий API делает сервер стенда по контракту из API.md.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

export function createMockApi(demoDataPath) {
  const ctx = { window: {} };
  vm.runInNewContext(readFileSync(demoDataPath, 'utf8'), ctx);
  const seed = JSON.parse(JSON.stringify(ctx.window.CABINET_DEMO));
  const db = {
    cases: seed.cases.cases, review: seed.cases.review, today: seed.cases.today,
    journal: seed.journal.items, knowledge: seed.knowledge, stats: seed.stats,
    settings: seed.settings, status: seed.status, sessions: new Map(), files: new Map(), n: 0
  };
  const now = () => new Date().toISOString();
  const inMin = (m) => new Date(Date.now() + m * 60000).toISOString();
  const hm = (iso) => { const d = new Date(iso); return d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0'); };
  const id = (p) => p + '-' + (++db.n).toString(36) + Date.now().toString(36).slice(-4);
  const TOPICS = ['Выставить счёт', 'Тендер или госзакупка', 'Статус заказа и документы', 'Ключ, активация, техническая поддержка', 'Задать вопрос'];

  function push(s, m) { const msg = { seq: ++s.seq, time: now(), from: 'agent', type: 'text', ...m }; s.messages.push(msg); return msg; }
  function event(s, actor, text, extra) { s.events.push({ actor, name: actor === 'client' ? 'Посетитель сайта' : undefined, time: now(), text, ...extra }); }

  function makeFile(name, title, lines) {
    const fid = id('f');
    db.files.set(fid, '<!doctype html><meta charset="utf-8"><title>' + name + '</title><body style="font:16px/24px Arial;max-width:720px;margin:40px auto">' +
      '<h1>' + title + '</h1>' + lines.map((l) => '<p>' + l + '</p>').join('') + '<p style="color:#888">Образец с локальной заглушки API, не настоящий документ</p></body>');
    return { name, url: '/support/api/files/' + fid, size_kb: 48 };
  }

  function handOver(s, text, kind) {
    const c = {
      id: id('case'), kind, status: 'waiting', deadline: inMin(db.settings.answer_min || 15), session_id: s.id,
      title: kind === 'answer' ? 'Вопрос без ответа в справке: ' + text.slice(0, 60) : 'Просьба клиента: ' + text.slice(0, 60),
      amount_rub: kind === 'approve' ? 92880 : undefined,
      desc: 'Посетитель сайта написал: «' + text + '»',
      advice: kind === 'answer' ? 'В справке нет точного ответа. Я не стал гадать и передал вопрос вам' : 'Прошлые заказы клиента оплачены вовремя, просьба в пределах обычных условий. Советую согласовать',
      recommend: 'approve',
      effect: kind === 'answer' ? 'Передаст клиенту ваш ответ в этом же чате' : 'Напишет клиенту, что вы согласовали, и пришлёт обновлённый счёт',
      approve_label: 'Согласовать', refuse_reasons: ['Не по условиям магазина'], refuse_reply: 'К сожалению, магазин не может согласовать эту просьбу. Если нужно, менеджер предложит другой вариант',
      reply_draft: '', events: s.events.slice()
    };
    db.cases.unshift(c);
    return c;
  }

  function agentReply(s, text, buttonId) {
    const t = (buttonId || text).toLowerCase();
    const out = [];
    const say = (m) => out.push(push(s, m));
    if (/спасибо|всё|все, пока|до свидания/.test(t)) { say({ type: 'close', text: 'Рад был помочь. Если появятся вопросы, пишите сюда' }); s.closed = true; }
    else if (/скидк|отсрочк|рассрочк/.test(t)) {
      const c = handOver(s, text, 'approve');
      say({ text: 'Такую просьбу решает менеджер. Передал ему вопрос, он ответит здесь до ' + hm(c.deadline) });
    } else if (/менеджер|человек|оператор/.test(t)) {
      say({ from: 'system', text: 'Подключаю менеджера' });
      setTimeout(() => push(s, { from: 'manager', author: 'Антон', text: 'Здравствуйте, это Антон, менеджер Store. Чем помочь?' }), 3000);
    } else if (/сч[её]т|кп|kaspersky|касперск|продл/.test(t)) {
      say({ text: 'Собрал КП и счёт по каталогу. Проверьте позиции, если всё верно, оплатите до срока в счёте' });
      say({ type: 'file', file: makeFile('Счёт № 2411-0457.pdf', 'Счёт № 2411-0457', ['Kaspersky Endpoint Security Стандартный, продление на 1 год, 40 узлов', 'Сумма 92 880 ₽']), buttons: [{ id: 'mail', text: 'Прислать на почту' }, { id: 'manager', text: 'Позвать менеджера' }] });
    } else if (/ключ|активац|скачать/.test(t)) {
      say({ text: 'Ключ приходит на почту из заказа в течение 15 минут после оплаты. Его же можно скачать в личном кабинете, раздел «Заказы»' });
    } else if (/macos|совместим|linux|требован/.test(t)) {
      const c = handOver(s, text, 'answer');
      say({ text: 'Точного ответа в справке нет, гадать не буду. Передал вопрос менеджеру, он ответит здесь до ' + hm(c.deadline) });
    } else if (buttonId === 'mail' || /почт/.test(t)) {
      say({ text: 'Отправил КП и счёт на почту из заказа. Письмо придёт в течение пяти минут' });
    } else {
      say({ text: 'Подскажу по заказу, счёту, продлению или ключам. Выберите тему или напишите вопрос своими словами', buttons: TOPICS.map((x, i) => ({ id: 't' + i, text: x })) });
    }
    out.forEach((m) => event(s, m.from === 'manager' ? 'manager' : 'agent', m.text || (m.file ? 'Прислал файл ' + m.file.name : '')));
    return out;
  }

  function toSession(c, text) {
    const s = c.session_id && db.sessions.get(c.session_id);
    if (s && !s.closed) { push(s, { text }); event(s, 'agent', text); }
  }

  const routes = [
    ['POST', /^\/chat\/sessions$/, (m, b) => {
      const s = { id: id('s'), seq: 0, messages: [], events: [], closed: false, page: b.page };
      db.sessions.set(s.id, s);
      push(s, { text: 'Здравствуйте! Я ИИ-помощник Softline Store. Выставлю счёт, найду заказ или подскажу по ключам. Сложное передам менеджеру', buttons: TOPICS.map((x, i) => ({ id: 't' + i, text: x })) });
      return [200, { session_id: s.id, messages: s.messages }];
    }],
    ['POST', /^\/chat\/sessions\/([^/]+)\/messages$/, (m, b) => {
      const s = db.sessions.get(m[1]); if (!s) return [404, { error: 'нет такого разговора' }];
      const client = { seq: ++s.seq, time: now(), from: 'client', type: 'text', text: String(b.text || '') };
      s.messages.push(client); event(s, 'client', client.text);
      return [200, { messages: [client, ...agentReply(s, client.text, b.button_id)] }];
    }],
    ['GET', /^\/chat\/sessions\/([^/]+)\/messages$/, (m, b, q) => {
      const s = db.sessions.get(m[1]); if (!s) return [404, { error: 'нет такого разговора' }];
      const after = Number(q.get('after') || 0);
      return [200, { messages: s.messages.filter((x) => x.seq > after) }];
    }],
    ['POST', /^\/chat\/sessions\/([^/]+)\/rating$/, () => [200, { ok: true }]],
    ['GET', /^\/files\/([^/]+)$/, (m) => db.files.has(m[1]) ? [200, db.files.get(m[1]), 'text/html; charset=utf-8'] : [404, { error: 'нет файла' }]],

    ['GET', /^\/cases$/, () => [200, { cases: db.cases, review: db.review, today: db.today }]],
    ['GET', /^\/cases\/([^/]+)\/events$/, (m) => { const c = db.cases.find((x) => x.id === m[1]); return c ? [200, { events: c.events || [] }] : [404, {}]; }],
    ['POST', /^\/cases\/([^/]+)\/decision$/, (m, b) => {
      const c = db.cases.find((x) => x.id === m[1]); if (!c) return [404, {}];
      if (c.status !== 'waiting') return [409, { error: 'уже решено', case: c }];
      c.decided_at = now(); c.decided_by = 'Антон';
      if (b.action === 'approve') { c.status = 'approved'; c.result = c.approve_result || 'Агент передал клиенту ваше согласие'; toSession(c, 'Менеджер согласовал вашу просьбу. Обновлённый счёт пришлю сюда и на почту'); }
      else if (b.action === 'refuse') { c.status = 'refused'; c.result = 'Агент ответил клиенту: ' + (b.reply_text || ''); toSession(c, b.reply_text || 'Менеджер не смог согласовать просьбу'); }
      else if (b.action === 'answer') {
        c.status = 'answered'; c.result = b.add_to_help ? 'Агент передал клиенту ваш ответ и добавил его в справку' : 'Агент передал клиенту ваш ответ';
        toSession(c, 'Ответ менеджера: ' + (b.reply_text || ''));
        if (b.add_to_help) db.knowledge.articles.unshift({ id: id('a'), title: c.title.replace(/^Вопрос без ответа в справке:\s*/, ''), meta: 'Вы добавили сегодня в ' + hm(now()) + ' из ответа клиенту', text: b.reply_text });
      } else return [400, { error: 'action: approve, refuse или answer' }];
      return [200, c];
    }],
    ['POST', /^\/rules$/, (m, b) => {
      const c = db.cases.find((x) => x.id === b.case_id); const p = b.params || {};
      const title = c && c.rule ? c.rule.text.map((x) => { const k = /^\{(\w+)\}$/.exec(x); return k ? Number(p[k[1]]).toLocaleString('ru-RU') : x; }).join(' ') : 'Новое правило';
      const r = { id: id('r'), title, meta: 'Такие просьбы агент согласует сам. Вы добавили правило сегодня в ' + hm(now()) };
      db.knowledge.rules.unshift(r); return [200, r];
    }],
    ['POST', /^\/rules\/([^/]+)$/, (m, b) => { const r = db.knowledge.rules.find((x) => x.id === m[1]); if (r) r.off = b.enabled === false; return [200, r || {}]; }],

    ['GET', /^\/journal$/, () => [200, { items: db.journal }]],
    ['GET', /^\/journal\/([^/]+)$/, (m) => { const it = db.journal.find((x) => x.id === m[1]); return it ? [200, it] : [404, {}]; }],
    ['POST', /^\/journal\/([^/]+)\/review$/, (m, b) => {
      const it = db.journal.find((x) => x.id === m[1]); if (!it) return [404, {}];
      it.review = false; db.review = db.review.filter((r) => r.id !== it.id);
      if (b.fix) db.knowledge.fixes.unshift({ id: id('f'), title: b.fix, meta: 'Вы поправили сегодня в ' + hm(now()) + ', разговор: ' + (it.client || '') });
      return [200, { ok: true }];
    }],

    ['GET', /^\/knowledge$/, () => [200, db.knowledge]],
    ['POST', /^\/knowledge\/pending\/([^/]+)\/add$/, (m) => {
      const k = db.knowledge, p = k.pending.find((x) => x.id === m[1]); if (!p) return [404, {}];
      k.pending = k.pending.filter((x) => x !== p); k.articles.unshift({ id: id('a'), title: p.title, meta: 'Вы добавили сегодня в ' + hm(now()) + ' из ответа менеджера' });
      return [200, { ok: true }];
    }],
    ['POST', /^\/knowledge\/articles$/, (m, b) => { const a = { id: id('a'), title: b.title, text: b.text, meta: 'Вы добавили сегодня в ' + hm(now()) }; db.knowledge.articles.unshift(a); db.knowledge.gaps = db.knowledge.gaps.filter((g) => g.title !== b.title); return [200, a]; }],
    ['PUT', /^\/knowledge\/articles\/([^/]+)$/, (m, b) => { const a = db.knowledge.articles.find((x) => x.id === m[1]); if (!a) return [404, {}]; a.text = b.text; a.meta = 'Вы обновили сегодня в ' + hm(now()); return [200, a]; }],
    ['DELETE', /^\/knowledge\/fixes\/([^/]+)$/, (m) => { db.knowledge.fixes = db.knowledge.fixes.filter((x) => x.id !== m[1]); return [200, { ok: true }]; }],

    ['GET', /^\/agent\/stats$/, () => [200, db.stats]],
    ['GET', /^\/agent\/settings$/, () => [200, db.settings]],
    ['PUT', /^\/agent\/settings$/, (m, b) => { Object.assign(db.settings, b); return [200, db.settings]; }],
    ['GET', /^\/agent\/status$/, () => [200, db.status]],
    ['POST', /^\/agent\/pause$/, (m, b) => { db.status = b.paused ? { state: 'paused', since: now() } : { state: 'on' }; return [200, db.status]; }]
  ];

  // req, res из node:http; path уже без префикса /support/api
  return async function handle(req, res, path, query) {
    let body = {};
    if (req.method !== 'GET') {
      let raw = ''; for await (const ch of req) raw += ch;
      try { body = raw ? JSON.parse(raw) : {}; } catch { body = {}; }
    }
    for (const [method, re, fn] of routes) {
      const m = re.exec(path);
      if (m && method === req.method) {
        const [code, data, type] = fn(m, body, query);
        res.writeHead(code, { 'Content-Type': type || 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(typeof data === 'string' ? data : JSON.stringify(data));
        return;
      }
    }
    res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'нет такого адреса в заглушке' }));
  };
}
