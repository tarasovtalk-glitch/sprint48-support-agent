"""Поиск по каталогу (таблица «запрос → товар», в том числе с опечатками) и строгая проверка цен
по каждому диалогу набора: любая сумма в ответе = цена позиции каталога × количество (скидка не больше 5 %)."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))
from ceny import CARD, PRICE, explained, kopecks  # noqa: E402
from eval.local import Chat, mini_catalog  # noqa: E402
from support_app.dialog import find_family, words  # noqa: E402

NABOR = [json.loads(line) for line in open(ROOT / 'eval' / 'nabor60.jsonl', encoding='utf-8')]


@pytest.fixture(scope='module')
def db():
    con = sqlite3.connect(mini_catalog())
    con.row_factory = sqlite3.Row
    yield con
    con.close()


SEARCH = [
    ('сколько стоит windows 11 pro', 'Windows 11 Pro'),
    ('виндовс 11 про для офиса', 'Windows 11 Pro'),
    ('нужен майкрософт офис для дома и учебы', 'Office для дома'),
    ('крипто про csp 5.0 бессрочная', 'КриптоПро CSP'),
    ('kripto pro csp', 'КриптоПро CSP'),
    ('криптоарм стандарт плюс', 'КриптоАРМ'),
    ('нужен mdaemon', 'MDaemon'),
    ('касперский для бизнеса стандартный', 'Kaspersky Endpoint Security для бизнеса Стандартный'),
    ('kes для бизнеса', 'Kaspersky Endpoint Security для бизнеса Стандартный'),
    ('anydesk на 1 год', 'AnyDesk'),
    ('анидеск', 'AnyDesk'),
    ('contentreader pdf 16 corp', 'ContentReader'),
    ('рутокен лайт 100 шт', 'Рутокен'),
    ('secret net studio', 'Secret Net'),
    # опечатки: одна переставленная, пропущенная, лишняя или соседняя буква
    ('касепрский для бизнеса', 'Kaspersky'),
    ('капсерского на 5 компьютеров', 'Kaspersky'),
    ('майкорсофт офис для дома', 'Office'),
    ('крипотпро csp 5.0', 'КриптоПро'),
    ('мультфактор на 200 пользователей', 'MULTIFACTOR'),
    ('аниидеск', 'AnyDesk'),
]


@pytest.mark.parametrize('query,expected', SEARCH)
def test_search_finds_product(db, query, expected):
    family, conf, _, _ = find_family(db, words(query), query)
    names = ' | '.join(o['name'] for o in family[:5])
    assert family and conf >= 0.5, f'{query!r}: ничего не нашёл'
    assert expected.lower() in names.lower(), f'{query!r} → {names[:200]}'


NOT_IN_CATALOG = [
    'windows server 2025 standard 16 ядер',
    'office 365 для организации',
    'adobe photoshop для юрлица',
    'pam indeed на 50 подключений',
]


@pytest.mark.parametrize('query', NOT_IN_CATALOG)
def test_search_does_not_invent_product(db, query):
    family, conf, _, _ = find_family(db, words(query), query)
    sellable = [o for o in family if o['available'] and o['price_kopecks']]
    assert not (sellable and conf >= 0.95), f'{query!r} → {family[0]["name"] if family else ""}'


@pytest.mark.parametrize('dialog', NABOR, ids=[d['id'] for d in NABOR])
def test_every_amount_comes_from_catalog(client, db, dialog):
    price_of = {r['id']: r['price_kopecks'] for r in db.execute('SELECT id, price_kopecks FROM products WHERE price_kopecks IS NOT NULL')}
    chat, seen = Chat(client), set()
    for i, turn in enumerate(dialog['turns']):
        r = chat.say(turn['client'], page=dialog.get('page', '') if i == 0 else '')
        text = ' '.join(m.get('text') or '' for m in (r.get('messages') or [])[-3:] if m.get('role') != 'client') or r.get('reply', '')
        own = {price_of[x] for x in CARD.findall(text) if x in price_of}
        seen |= own
        for m in PRICE.finditer(text):
            assert explained(kopecks(m.group(1)), own or seen), f'{dialog["id"]} ход {i + 1}: {m.group(0)} не из каталога — {text[:200]}'
