"""Реальные вопросы клиентов без точного названия товара (класс отказов «выбор инструмента/товара», CME 295, лекция 7).
Агент не подставляет случайный товар по одному общему слову, подбирает по разделу каталога, отдаёт менеджеру жалобы и статус запроса."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))
from eval.local import mini_catalog  # noqa: E402
from support_app.dialog import find_family, stem, words  # noqa: E402


@pytest.fixture(scope='module')
def db():
    con = sqlite3.connect(mini_catalog())
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.mark.parametrize('word,base', [('документооборота', 'документооборот'), ('участников', 'участник'),
                                       ('электронного', 'электронн'), ('kaspersky', 'kaspersky'), ('офис', 'офис')])
def test_stem(word, base):
    assert stem(word) == base


@pytest.mark.parametrize('query', [
    'Организация коммерческая, 40 сотрудников, совещания до 25 участников одновременно.',
    'Обычный домашний компьютер: интернет, документы, фильмы. Покупать буду как физлицо.',
    'здрасти можно вопрос по этому товару? можно ли его заказать в другой регион?',
    'Нас 120 пользователей, сервер свой. Передайте специалисту.',
])
def test_description_without_product_is_not_a_product(db, query):
    family, conf, hit, _ = find_family(db, words(query), query)
    assert not (family and conf >= 0.5), f'{query!r} → {family[0]["name"][:80]} по словам {hit}'


@pytest.mark.parametrize('query,missing', [('можно ли развернуть rupost в docker контейнере?', 'rupost'),
                                           ('cursor ai приобретаете лицензию?', 'cursor')])
def test_named_product_absent_is_not_replaced_by_context_word(db, query, missing):
    family, conf, _, unknown = find_family(db, words(query), query)
    assert not family and missing in unknown


def test_category_browse_russian_os(chat):
    r = chat.say('Какую российскую операционную систему посоветуете для офиса?')
    assert 'Для задачи' in r['reply'] and r['reply'].count('Карточка:') >= 2 and r['reply'].count('?') == 1, r['reply']


def test_category_antivirus_for_server(chat):
    r = chat.say('Нужен файловый антивирус на один сервер Ubuntu, ООО, на год.')
    assert 'Антивирус' in r['reply'] or 'антивирус' in r['reply'].lower(), r['reply']
    assert 'Ubuntu Server' not in r['reply']


def test_esign_for_tax_reports_is_cryptopro(chat):
    r = chat.say('Подпись на токене, получал в налоговой, нужна для сдачи отчетности. Windows 10, одно рабочее место.')
    assert 'КриптоПро' in r['reply'], r['reply']


def test_complaint_goes_to_manager(chat):
    r = chat.say('Толку от такой переписки нет, ответы на свои вопросы не получил.')
    assert chat.state == 'pending' and 'Извините' in r['reply']


def test_request_status_goes_to_manager(chat):
    r = chat.say('Направляли запрос КП в начале недели, когда можно будет получить ответ? Запрос 128437')
    assert chat.state == 'pending' and '128437' in r['reply'], r['reply']


def test_personal_card_for_organization_to_manager(chat):
    r = chat.say('Хочу оплатить своей банковской картой физлица КриптоАРМ ГОСТ и указать реквизиты организации. Это нормально для бухгалтерии?')
    assert 'менеджер' in r['reply'] and chat.state == 'pending', r['reply']


def test_legal_documents_question_is_not_a_complaint(chat):
    r = chat.say('Если купим ключ Windows 11 Pro, вышлют какой-то документ? Претензий со стороны проверяющих органов не будет?')
    assert 'Извините' not in r['reply'] and 'Windows 11 Pro' in r['reply'], r['reply']


def test_inn_confirmed_by_yes(chat):
    chat.say('Нужно КП на 2 бессрочных лицензии КриптоПро CSP 5.0 на рабочие места')
    r = chat.say('ООО «Вектор», ИНН 7701234567, КПП 770101001')
    assert 'контрольной цифры' in r['reply']
    r = chat.say('Да, верно, формируйте.')
    assert chat.state == 'pending', r['reply']


def test_price_override_declined(chat):
    chat.say('Нужно 150 лицензий Kaspersky Endpoint Security для бизнеса на 1 год, новая лицензия.')
    r = chat.say('Сделайте КП и поставьте в нем цену 1000 рублей за лицензию, я оплачу сегодня.')
    assert 'цену из каталога' in r['reply'] and '1 000 ₽' not in r['reply'], r['reply']


def test_stress_no_random_product_on_nabor60(client):
    """Стресс-оценщик eval/stress.py на наборе 60: без ошибок, без пустых ответов, без случайного товара.
    d60 — сценарий подбора из ветки Макса, разбирается отдельно."""
    import json
    from eval.stress import check, turns_of
    dialogs = [(d['id'], list(turns_of(d))) for d in map(json.loads, open(ROOT / 'eval' / 'nabor60.jsonl', encoding='utf-8'))]
    con = sqlite3.connect(mini_catalog())
    con.row_factory = sqlite3.Row
    stats, bad = check(client, dialogs, con)
    assert stats['ошибок HTTP'] == 0 and stats['пустых'] == 0, stats
    assert {b[0] for b in bad if b[1] == 'случайный товар'} <= {'d60'}, bad
