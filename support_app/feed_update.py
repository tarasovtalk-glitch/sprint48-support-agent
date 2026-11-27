"""Ежедневное обновление каталога из фида без простоя и без риска сломать стенд.

Порядок: фид → новый индекс во временном файле рядом → проверки → копия текущего индекса в *.prev → атомарная замена.
Приложение открывает индекс на каждый запрос заново, поэтому новый каталог виден сразу, перезапуск не нужен.
Проверки не прошли — текущий каталог не трогаем, код выхода 1. Откат: --rollback возвращает *.prev.

    python -m support_app.feed_update путь/или/https://адрес/фида.xml /data/catalog.sqlite3
    python -m support_app.feed_update --rollback /data/catalog.sqlite3

Расписание (пример для cron на сервере, раз в сутки в 05:00 МСК):
    0 5 * * * cd /app && python -m support_app.feed_update "$SUPPORT_FEED_URL" /data/catalog.sqlite3 >> /data/feed_update.log 2>&1
"""
import argparse
import fcntl
import gzip
import re
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
from contextlib import closing
from pathlib import Path

from .catalog import import_catalog

MIN_SHARE = 0.9          # новый фид не меньше 90 % позиций прежнего: обрезанная выгрузка не заменит рабочий каталог
MIN_OFFERS = 1           # пустой фид — всегда отказ


def fetch(source: str, folder: Path) -> Path:
    """Локальный файл или адрес http(s); сжатый gzip распаковывается."""
    raw = folder / 'feed.raw'
    if source.startswith(('http://', 'https://')):
        with urllib.request.urlopen(source, timeout=300) as response, raw.open('wb') as out:  # noqa: S310 — адрес задаёт администратор
            shutil.copyfileobj(response, out)
    else:
        shutil.copyfile(source, raw)
    with raw.open('rb') as f:
        packed = f.read(2) == b'\x1f\x8b'
    if not packed:
        return raw
    plain = folder / 'feed.xml'
    with gzip.open(raw, 'rb') as src, plain.open('wb') as out:
        shutil.copyfileobj(src, out)
    return plain


def stats(path: Path) -> dict:
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        meta = dict(db.execute('SELECT name, value FROM metadata').fetchall())
        return {
            'offers': db.execute('SELECT count(*) FROM products').fetchone()[0],
            'available': db.execute('SELECT count(*) FROM products WHERE available=1').fetchone()[0],
            'searchable': db.execute("SELECT count(*) FROM product_search WHERE product_search MATCH 'windows OR kaspersky OR astra OR 1с'").fetchone()[0],
            'source_date': meta.get('source_date', ''),
            'loaded_at': meta.get('loaded_at', ''),
        }


DATE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def check(new: dict, old: dict | None, min_share: float) -> list[str]:
    problems = []
    if new['offers'] < MIN_OFFERS:
        problems.append('в фиде нет позиций')
    if not DATE.match(new['source_date'] or ''):
        problems.append(f'дата выгрузки не распознана: «{new["source_date"]}»')
    elif old and DATE.match(old['source_date'] or '') and new['source_date'][:16] < old['source_date'][:16]:
        problems.append(f'фид старее текущего: {new["source_date"]} < {old["source_date"]}')
    if new['available'] == 0:
        problems.append('нет ни одной позиции с ценой')
    if new['searchable'] == 0 and new['offers'] >= 100:
        problems.append('поиск по каталогу пуст')
    if old and new['offers'] < old['offers'] * min_share:
        problems.append(f'позиций {new["offers"]} — меньше {min_share:.0%} от прежних {old["offers"]}')
    if old and new['available'] < old['available'] * min_share:
        problems.append(f'позиций с ценой {new["available"]} — меньше {min_share:.0%} от прежних {old["available"]}')
    if old and old['searchable'] and new['searchable'] < old['searchable'] * min_share:
        problems.append(f'поиск находит {new["searchable"]} — меньше {min_share:.0%} от прежних {old["searchable"]}')
    return problems


class locked:
    """Обновление и откат — по одному: второй запуск ждёт, пока первый закончит."""
    def __init__(self, target: Path):
        self.path = target.with_name(target.name + '.lock')

    def __enter__(self):
        self.file = self.path.open('a')
        fcntl.flock(self.file, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


def backup(target: Path):
    """Копия текущего каталога в *.prev появляется целиком или не появляется: сначала временный файл, потом атомарная замена."""
    prev = target.with_name(target.name + '.prev')
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix='.prev-')
    os.close(fd)
    try:
        shutil.copy2(target, tmp)
        os.replace(tmp, prev)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def update(source: str, target: Path, min_share: float = MIN_SHARE) -> dict:
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with locked(target):
        return _update(source, target, min_share)


def _update(source: str, target: Path, min_share: float) -> dict:
    old = stats(target) if target.is_file() else None
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.feed-') as work:
        folder = Path(work)
        fresh = folder / 'catalog.sqlite3'
        import_catalog(fetch(source, folder), fresh)
        with closing(sqlite3.connect(fresh)) as db, db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('loaded_at', time.strftime('%Y-%m-%dT%H:%M:%S%z')))
        new = stats(fresh)
        problems = check(new, old, min_share)
        if problems:
            return {'updated': False, 'problems': problems, 'new': new, 'old': old}
        if old:
            backup(target)
        os.replace(fresh, target)   # атомарно: запрос видит либо старый, либо новый каталог целиком
    return {'updated': True, 'problems': [], 'new': new, 'old': old}


def rollback(target: Path) -> bool:
    target = target.resolve()
    with locked(target):
        prev = target.with_name(target.name + '.prev')
        if not prev.is_file():
            return False
        os.replace(prev, target)   # .prev всегда целый: его пишет backup() через временный файл
        return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Безопасное обновление каталога из фида Softline.')
    parser.add_argument('source', nargs='?', help='путь к фиду или адрес http(s)')
    parser.add_argument('target', type=Path)
    parser.add_argument('--min-share', type=float, default=MIN_SHARE)
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args(argv)
    if args.rollback:
        ok = rollback(args.target)
        print('откат выполнен' if ok else 'нет копии *.prev — откатывать нечего')
        return 0 if ok else 1
    if not args.source:
        parser.error('нужен источник фида')
    result = update(args.source, args.target, args.min_share)
    if result['updated']:
        print(f'каталог обновлён: {result["new"]["offers"]} позиций, в наличии {result["new"]["available"]}, фид от {result["new"]["source_date"]}')
        return 0
    print('каталог НЕ обновлён, текущий оставлен: ' + '; '.join(result['problems']), file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
