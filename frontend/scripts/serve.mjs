// Локальная проверка: сайт по адресу http://localhost:8080/support/, кабинет на /support/cabinet/.
//   npm start            файлы из src и заглушка API на /support/api
//   npm run preview      то же из dist (сначала npm run build)
//   --no-mock            без заглушки: проверить, как интерфейс ведёт себя без сервера
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createMockApi } from './mock-api.mjs';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const args = process.argv.slice(2);
const dir = path.join(root, args.includes('--dist') ? 'dist' : 'src');
const mock = args.includes('--no-mock') ? null : createMockApi(path.join(root, 'src/cabinet/demo-data.js'));
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
    if (mock) return mock(req, res, p.slice(BASE.length + 3), url.searchParams);
    res.writeHead(503); res.end(); return;
  }
  let file = path.join(dir, path.normalize(p.slice(BASE.length)).replace(/^(\.\.[/\\])+/, ''));
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
}).listen(port, () => console.log(`http://localhost:${port}${BASE}  и  http://localhost:${port}${BASE}cabinet/${mock ? '  (заглушка API на ' + BASE + 'api)' : '  (без API)'}`));
