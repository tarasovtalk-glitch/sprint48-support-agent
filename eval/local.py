"""Локальный стенд для тестов и прогона набора: то же приложение, что на сервере, без сети и без модели.

Каталог: переменная SUPPORT_CATALOG_DATABASE или tests/data/catalog-mini.sqlite3 (собирается из tests/data/feed-mini.yml).
Модель не вызывается: ключ пустой, поэтому model.completion возвращает None и ответы детерминированы.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_KEY = 'test-demo-key-0123456789abcdef'  # тестовое значение, не ключ стенда
FONTS = ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf',
         'C:/Windows/Fonts/arial.ttf')


def mini_catalog() -> Path:
    out = ROOT / 'tests' / 'data' / 'catalog-mini.sqlite3'
    feed = ROOT / 'tests' / 'data' / 'feed-mini.yml'
    if not out.exists() or out.stat().st_mtime < feed.stat().st_mtime:
        from support_app.catalog import import_catalog
        out.unlink(missing_ok=True)
        import_catalog(feed, out)
    return out


def make_client(catalog: Path | None = None):
    from fastapi.testclient import TestClient
    from support_app.app import create_app

    work = Path(tempfile.mkdtemp(prefix='smf-local-'))
    os.environ['SUPPORT_CHAT_ONLY'] = '1'
    os.environ['SUPPORT_DEMO_KEY'] = DEMO_KEY
    os.environ['YANDEX_API_KEY'] = ''
    os.environ['YANDEX_MODEL_URI'] = ''
    os.environ['SUPPORT_PDF_FONT'] = next(f for f in FONTS if Path(f).is_file())
    env_catalog = os.environ.get('SMF_CATALOG')
    os.environ['SUPPORT_CATALOG_DATABASE'] = str(catalog or (Path(env_catalog) if env_catalog else mini_catalog()))
    return TestClient(create_app(work / 'support.sqlite3'))


class Chat:
    """Один разговор клиента: Chat(client).say('...') -> ответ API."""

    def __init__(self, client):
        self.client = client
        r = client.post('/support/api/sessions', headers={'X-Demo-Key': DEMO_KEY})
        assert r.status_code == 201, r.text
        self.token = r.json()['session_token']
        self.last = None

    def say(self, text=None, *, action=None, value='', page=''):
        body = {'text': text} if text is not None else {'action': action, 'value': value}
        if page:
            body['page_url'] = page if page.startswith('http') else 'https://' + page
        r = self.client.post('/support/api/case/messages', json=body, headers={'Authorization': 'Bearer ' + self.token})
        self.last = r
        return r.json() if r.headers.get('content-type', '').startswith('application/json') else {'status': r.status_code}

    @property
    def state(self):
        return (self.last.json().get('case') or {}).get('state')


def run_set(nabor: Path, out: Path, catalog: Path | None = None):
    """Прогон набора локально; формат вывода как у eval/progon.py, чтобы работал eval/ocenka.py."""
    client = make_client(catalog)
    with open(out, 'w', encoding='utf-8') as f:
        for line in open(nabor, encoding='utf-8'):
            d = json.loads(line)
            chat = Chat(client)
            rec = {'id': d['id'], 'session_status': 201, 'turns': []}
            for i, t in enumerate(d['turns']):
                resp = chat.say(t['client'], page=d.get('page', '') if i == 0 else '')
                rec['turns'].append({'client': t['client'], 'status': chat.last.status_code, 'sec': 0, 'resp': resp})
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    run_set(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
