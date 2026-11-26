import argparse
import json
import re
import sqlite3
from contextlib import closing
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from defusedxml.ElementTree import iterparse


SCHEMA = '''
CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE products (
    id TEXT PRIMARY KEY, family TEXT NOT NULL, name TEXT NOT NULL,
    vendor TEXT NOT NULL, category TEXT NOT NULL, sku TEXT, url TEXT,
    price_kopecks INTEGER, available INTEGER NOT NULL,
    min_users INTEGER, max_users INTEGER, term_months INTEGER,
    registry TEXT, parameters TEXT NOT NULL, new_purchase INTEGER NOT NULL
);
CREATE VIRTUAL TABLE product_search USING fts5(
    name, vendor, category, details, content='', tokenize='unicode61 remove_diacritics 2'
);
'''

IGNORED_VALUES = {'', 'не определено', 'другое или отсутствует', 'нет данных'}
DETAIL_FIELDS = ('Версия', 'Срок действия', 'Тип лицензии', 'Пользователь', 'Тип организации', 'Способ доставки',
                 'Совместимая архитектура/платформа', 'Номер записи в реестре отечественного ПО',
                 'К-во пользователей от', 'К-во пользователей до')
LICENSE_UNITS = r'(?:пользовател\w*|сотрудник\w*|устройств\w*|уз(?:ел|л\w*)|рабоч\w*\s+станци\w*|users?|nodes?)'
EXPANSION_OR_MEDIA = r'продлен|миграц|renewal|upgrade|переход с|докуп|active\s*sync|медиапакет|комплект документации'


def normalize(value: str) -> str:
    return value.casefold().replace('ё', 'е')


def number(value: str | None) -> int | None:
    match = re.fullmatch(r'\s*(\d{1,6})\s*', value or '')
    return int(match.group(1)) if match else None


def price_kopecks(raw: str, currency: str) -> int | None:
    if currency not in {'RUB', 'RUR'}:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value.is_finite() and 0 < value < 1_000_000_000:
        return int(value * 100) if value * 100 == int(value * 100) else None
    return None


def product_url(raw: str) -> str | None:
    parsed = urlsplit(raw)
    if parsed.scheme == 'https' and parsed.netloc == 'store.softline.ru' and parsed.path.startswith('/'):
        return f'https://store.softline.ru{parsed.path}'
    return None


def user_range(title: str, params: dict[str, str]) -> tuple[int | None, int | None]:
    low = number(params.get('К-во пользователей от'))
    high = number(params.get('К-во пользователей до'))
    if high is not None:
        return low, high
    normalized = normalize(title)
    span = re.search(rf'\b(?:от\s*)?(\d{{1,5}})\s*(?:до|[-–])\s*(\d{{1,5}})\s+{LICENSE_UNITS}', normalized)
    if span:
        return int(span.group(1)), int(span.group(2))
    exact = re.search(rf'\b(\d{{1,5}})\s+{LICENSE_UNITS}', normalized)
    return low, int(exact.group(1)) if exact else None


def add_offer(db: sqlite3.Connection, node, categories: dict[str, str]):
    offer_id = node.get('id')
    title = node.findtext('name', '').strip()
    if not offer_id or not title:
        return

    params = {}
    for item in node.findall('param'):
        value = (item.text or '').strip()
        key = item.get('name', '')
        if key in DETAIL_FIELDS and normalize(value) not in IGNORED_VALUES:
            params[key] = value[:160]
    term = re.fullmatch(r'(\d{1,3})\s*мес\.?', normalize(params.get('Срок действия', '')))
    registry = params.get('Номер записи в реестре отечественного ПО', '')
    vendor = node.findtext('vendor', '').strip()
    category = categories.get(node.findtext('categoryId', ''), '')
    min_users, max_users = user_range(title, params)
    new_purchase = not re.search(EXPANSION_OR_MEDIA, normalize(f'{title} {params.get("Тип лицензии", "")}'))
    cursor = db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
        offer_id, node.get('group_id') or offer_id, title, vendor, category,
        node.findtext('vendorCode', '').strip() or None,
        product_url(node.findtext('url', '')),
        price_kopecks(node.findtext('price', ''), node.findtext('currencyId', '')),
        int(node.get('available') == 'true'),
        min_users, max_users,
        int(term.group(1)) if term else None, registry if number(registry) else None,
        json.dumps(params, ensure_ascii=False), int(new_purchase),
    ))
    description = re.sub(r'<[^>]{0,300}>', ' ', node.findtext('description', '')[:1200])
    db.execute('INSERT INTO product_search(rowid,name,vendor,category,details) VALUES(?,?,?,?,?)', (
        cursor.lastrowid, normalize(title), normalize(vendor), normalize(category), normalize(description),
    ))


def import_catalog(source: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    stack = []
    categories = {}
    with closing(sqlite3.connect(output)) as db, db:
        db.executescript(SCHEMA)
        for event, node in iterparse(source, events=('start', 'end'), forbid_dtd=False, forbid_entities=True, forbid_external=True):
            if event == 'start':
                stack.append(node)
                if node.tag == 'yml_catalog':
                    db.execute('INSERT INTO metadata VALUES(?,?)', ('source_date', node.get('date', '')))
                continue
            if node.tag == 'category':
                categories[node.get('id', '')] = (node.text or '').strip()
                stack[-2].remove(node)
            elif node.tag == 'offer':
                add_offer(db, node, categories)
                stack[-2].remove(node)
            stack.pop()
        print(db.execute('SELECT count(*) FROM products').fetchone()[0], 'offers indexed')


def read_only(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def view(row: sqlite3.Row) -> dict:
    item = dict(row)
    item.pop('rank', None)
    item['available'] = bool(item['available'])
    item['parameters'] = json.loads(item['parameters'])
    return item


def find_matches(db: sqlite3.Connection, terms: list[str], users: int | None, months: int | None, *, active_only=False, new_purchase_only=False) -> list[dict]:
    tokens = re.findall(r'[^\W_]+', normalize(' '.join(terms)), flags=re.UNICODE)[:10]
    if not tokens:
        return []
    expression = ' AND '.join(f'"{token}"' for token in dict.fromkeys(tokens))
    rows = db.execute('''
        SELECT p.*, bm25(product_search, 11.0, 4.0, 3.0, 0.15) AS rank
        FROM product_search JOIN products p ON p.rowid=product_search.rowid
        WHERE product_search MATCH ?
          AND (? IS NULL OR ((p.max_users IS NULL OR p.max_users >= ?) AND (p.min_users IS NULL OR p.min_users <= ?)))
          AND (? IS NULL OR p.term_months IS NULL OR p.term_months=?)
          AND (?=0 OR p.available=1)
          AND (?=0 OR p.new_purchase=1)
        ORDER BY p.available DESC,
                 CASE WHEN ? IS NOT NULL AND p.max_users IS NOT NULL THEN 0 ELSE 1 END,
                 rank, p.price_kopecks IS NULL, p.price_kopecks
        LIMIT 24
    ''', (expression, users, users, users, months, months, int(active_only), int(new_purchase_only), users)).fetchall()
    return [view(row) for row in rows]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build a read-only search index from the Softline XML feed.')
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    import_catalog(args.source, args.output)
