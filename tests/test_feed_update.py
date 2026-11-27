"""Ежедневное обновление фида: новый каталог заменяет старый только после проверок; обрезанный фид не ломает стенд; есть откат."""
import gzip
import re
from pathlib import Path

from support_app.feed_update import main, stats, update

FEED = Path(__file__).parent / 'data' / 'feed-mini.yml'


def cut_feed(tmp: Path, keep: int) -> Path:
    """Фид с первыми keep позициями — как обрезанная выгрузка."""
    text = FEED.read_text(encoding='utf-8')
    offers = re.findall(r'<offer\b.*?</offer>', text, re.S)
    for o in offers[keep:]:
        text = text.replace(o, '')
    out = tmp / f'feed-{keep}.yml'
    out.write_text(text, encoding='utf-8')
    return out


def test_first_load_and_status(tmp_path, client):
    target = tmp_path / 'catalog.sqlite3'
    result = update(str(FEED), target)
    assert result['updated'] and target.is_file(), result
    s = stats(target)
    assert s['offers'] > 0 and s['source_date'] and s['loaded_at']


def test_truncated_feed_keeps_current_catalog(tmp_path):
    target = tmp_path / 'catalog.sqlite3'
    update(str(FEED), target)
    before = stats(target)
    result = update(str(cut_feed(tmp_path, 2)), target)
    assert not result['updated'] and 'меньше' in ' '.join(result['problems']), result
    assert stats(target)['offers'] == before['offers']


def test_gzip_feed_and_rollback(tmp_path):
    target = tmp_path / 'catalog.sqlite3'
    update(str(FEED), target)
    first = stats(target)['loaded_at']
    packed = tmp_path / 'feed.yml.gz'
    packed.write_bytes(gzip.compress(FEED.read_bytes()))
    assert main([str(packed), str(target)]) == 0
    assert (tmp_path / 'catalog.sqlite3.prev').is_file()
    assert main(['--rollback', str(target)]) == 0
    assert stats(target)['loaded_at'] == first


def test_broken_feed_does_not_touch_catalog(tmp_path):
    target = tmp_path / 'catalog.sqlite3'
    update(str(FEED), target)
    bad = tmp_path / 'bad.yml'
    bad.write_text('<yml_catalog date="2026-11-27"><shop><offers></offers></shop></yml_catalog>', encoding='utf-8')
    assert main([str(bad), str(target)]) == 1
    assert stats(target)['offers'] > 0


def test_catalog_status_endpoint(client):
    r = client.get('/support/api/catalog/status')
    assert r.status_code == 200 and r.json()['offers'] > 0 and r.json()['source_date'], r.text
