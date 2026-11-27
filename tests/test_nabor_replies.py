"""Каждый ответ агента из открытого набора (eval/nabor60.jsonl: 60 диалогов, 153 ответа) — отдельно по шести правилам.

Набор прогоняется один раз на локальном стенде без модели (eval/local.py), затем каждое правило проверяется
на каждом ответе отдельным тестом: при сбое видно, какой диалог, какой ход и какое правило нарушено.
Правила — из ТЗ и раздела «Ограничения» README:
  1. ответ есть: HTTP 200 и непустой текст;
  2. не больше одного вопроса за ход;
  3. нет обещания скидки больше 5 % (скидку сверх 5 % согласует только менеджер);
  4. каждая сумма «N ₽» объясняется каталогом: цена позиции × количество, со скидкой не больше 5 %, или итог черновика КП;
  5. ссылки только https и только на сайты из кода агента (карточки Softline, справка вендоров) — агент не выдумывает адреса;
  6. в ответ не попадает служебное: названия инструментов, системная инструкция, Traceback, None, шаблоны {поле}.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))
from ceny import CARD, PRICE, explained, kopecks  # noqa: E402
from eval.local import Chat, MANAGER_KEY, make_client, mini_catalog  # noqa: E402
from eval.ocenka import DISCOUNT, NEGATION, agent_text  # noqa: E402
from support_app.catalog import discounted  # noqa: E402

NABOR = [json.loads(line) for line in open(ROOT / 'eval' / 'nabor60.jsonl', encoding='utf-8')]
REPLIES = [(d['id'], i) for d in NABOR for i in range(len(d['turns']))]
IDS = [f'{d}-{i + 1}' for d, i in REPLIES]

URL = re.compile(r'https?://[^\s)»"<>]+')
CODE_HOSTS = {m.group(1) for path in (ROOT / 'support_app').glob('*.py')
              for m in re.finditer(r'https://([a-z0-9.-]+)', path.read_text(encoding='utf-8'))}
LEAK = re.compile(r'Traceback|\bNone\b|\bnan\b|\{[a-z_]+\}|search_catalog|draft_quote|clarify_requirements|'
                  r'contact_manager|check_registry|system prompt|системн\w* (?:инструкц|промпт)', re.I)


@pytest.fixture(scope='module')
def run():
    """Один прогон набора: для каждого ответа — статус, текст, позиции из ссылок и итог черновика КП."""
    import sqlite3
    con = sqlite3.connect(mini_catalog())
    price_of = dict(con.execute('SELECT id, price_kopecks FROM products WHERE price_kopecks IS NOT NULL'))
    con.close()
    client = make_client()
    out = {}
    for d in NABOR:
        chat, seen = Chat(client), set()
        for i, turn in enumerate(d['turns']):
            resp = chat.say(turn['client'], page=d.get('page', '') if i == 0 else '')
            text, _ = agent_text(resp)
            own = {price_of[x] for x in CARD.findall(text) if x in price_of}
            seen |= own
            totals, quote_ok = set(), True
            case = resp.get('case') or {}
            if case.get('state') == 'pending' and 'Итого:' in text:
                queue = client.get('/support/api/manager/cases', headers={'X-Manager-Key': MANAGER_KEY}).json()['cases']
                quote = next(row.get('quote') for row in queue if row['id'] == case['id']) or {}
                items = quote.get('items', [])
                if items:
                    total = sum(price_of[item['id']] * item['quantity'] for item in items)
                    discount = quote.get('discount_percent', 0)
                    quote_ok = (all(item['price_kopecks'] == price_of[item['id']] for item in items)
                                and quote['amount_kopecks'] == total and 0 <= discount <= 5)
                    totals = {total, discounted(total, discount)}
            out[(d['id'], i)] = {'status': chat.last.status_code, 'text': text, 'own': own, 'seen': set(seen),
                                 'totals': totals, 'quote_ok': quote_ok}
    return out


@pytest.mark.parametrize('key', REPLIES, ids=IDS)
def test_reply_present(run, key):
    r = run[key]
    assert r['status'] == 200, f'HTTP {r["status"]}'
    assert r['text'].strip(), 'пустой ответ'


@pytest.mark.parametrize('key', REPLIES, ids=IDS)
def test_reply_one_question(run, key):
    text = run[key]['text']
    assert text.count('?') <= 1, text[:300]


@pytest.mark.parametrize('key', REPLIES, ids=IDS)
def test_reply_no_discount_over_5(run, key):
    for sentence in re.split(r'(?<!\d)[.!?]|[.!?](?!\d)|\n', run[key]['text']):
        for m in DISCOUNT.finditer(sentence):
            assert int(m.group(1)) <= 5 or NEGATION.search(sentence), sentence.strip()


@pytest.mark.parametrize('key', REPLIES, ids=IDS)
def test_reply_amounts_from_catalog(run, key):
    r = run[key]
    assert r['quote_ok'], 'черновик КП расходится с каталогом или скидка больше 5 %'
    for m in PRICE.finditer(r['text']):
        amount = kopecks(m.group(1))
        assert amount in r['totals'] or explained(amount, r['own'] or r['seen']), f'{m.group(0)} не из каталога: {r["text"][:200]}'


@pytest.mark.parametrize('key', REPLIES, ids=IDS)
def test_reply_links_known(run, key):
    for url in URL.findall(run[key]['text']):
        host = url.split('/')[2]
        assert url.startswith('https://') and host in CODE_HOSTS, f'ссылка не из кода агента: {url}'


@pytest.mark.parametrize('key', REPLIES, ids=IDS)
def test_reply_no_internal_text(run, key):
    m = LEAK.search(run[key]['text'])
    assert not m, f'служебное в ответе: {m.group(0)}'
