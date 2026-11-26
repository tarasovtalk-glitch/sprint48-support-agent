// Сборка: копирует src в dist и пишет dist/config.js из переменных окружения.
//   API_BASE  адрес API агента, по умолчанию /support/api
//   DEMO=1    чат и кабинет работают на примере данных, без сервера
// Ключей здесь нет и быть не должно: модель и почту вызывает только сервер.
import { cp, rm, writeFile, readdir, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const src = path.join(root, 'src');
const dist = path.join(root, 'dist');

const apiBase = (process.env.API_BASE || '/support/api').replace(/\/$/, '');
const demo = process.env.DEMO === '1' || process.env.DEMO === 'true';

await rm(dist, { recursive: true, force: true });
await cp(src, dist, { recursive: true });
await writeFile(path.join(dist, 'config.js'),
  '// Создано сборкой. Можно поправить на сервере без пересборки.\n' +
  'window.SUPPORT_CONFIG = ' + JSON.stringify({ apiBase, demo }) + ';\n');

async function size(dir) {
  let total = 0, files = 0;
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { const s = await size(p); total += s.total; files += s.files; }
    else { total += (await stat(p)).size; files++; }
  }
  return { total, files };
}
const s = await size(dist);
console.log(`dist/ готов: ${s.files} файлов, ${(s.total / 1048576).toFixed(1)} МБ. API: ${apiBase}${demo ? ', демо-режим' : ''}`);
