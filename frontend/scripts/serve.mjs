// Локальная проверка: сайт по адресу http://localhost:8080/support/, кабинет на /support/cabinet/.
//   npm start            файлы из src, запросы /support/api идут на сервер агента
//   npm run preview      то же из dist (сначала npm run build)
//   --no-api             без сервера: проверить, как интерфейс ведёт себя, если API не отвечает
// Сервер агента: SUPPORT_API (по умолчанию http://127.0.0.1:8000). X-Demo-Key берётся из SUPPORT_DEMO_KEY
// и подставляется только в POST /support/api/sessions, как это делает Caddy на стенде. В браузер ключ не попадает.
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const args = process.argv.slice(2);
const dir = path.join(root, args.includes('--dist') ? 'dist' : 'src');
const api = args.includes('--no-api') ? null : new URL(process.env.SUPPORT_API || 'http://127.0.0.1:8000');
const demoKey = process.env.SUPPORT_DEMO_KEY || '';
const port = Number(process.env.PORT || 8080);
const BASE = '/support/';
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.ico': 'image/x-icon',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let p = decodeURIComponent(url.pathname);
  if (!p.startsWith(BASE)) { res.writeHead(302, { Location: BASE }); res.end(); return; }
  if (p.startsWith(BASE + 'api/')) {
    if (!api) { res.writeHead(503); res.end(); return; }
    const headers = { ...req.headers, host: api.host };
    delete headers['x-demo-key'];
    if (demoKey && req.method === 'POST' && url.pathname === BASE + 'api/sessions') headers['x-demo-key'] = demoKey;
    const up = http.request({ hostname: api.hostname, port: api.port, path: req.url, method: req.method, headers }, (r) => {
      res.writeHead(r.statusCode, r.headers); r.pipe(res);
    });
    up.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end(); });
    req.pipe(up); return;
  }
  const relative = p.slice(BASE.length).replace(/^softline-test\//, '');
  let file = path.join(dir, path.normalize(relative).replace(/^(\.\.[/\\])+/, ''));
  if (!file.startsWith(dir)) { res.writeHead(403); res.end(); return; }
  try {
    if ((await stat(file)).isDirectory()) {
      if (!p.endsWith('/')) { res.writeHead(301, { Location: p + '/' + url.search }); res.end(); return; }
      file = path.join(file, 'index.html');
    }
    const data = await readFile(file);
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
    res.end(data);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('Нет такого файла');
  }
}).listen(port, () => console.log(`http://localhost:${port}${BASE}  и  http://localhost:${port}${BASE}cabinet/${api ? '  (API: ' + api.origin + ')' : '  (без API)'}`));
