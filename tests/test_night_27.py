"""Доработки ночи 27.11 (проверка Codex, круги 1–2): кнопки, срок по умолчанию, после покупки, КП, сводка, обновление фида."""
from conftest import REQ  # noqa: F401


def labels(r):
    return [b['label'] if isinstance(b, dict) else b[0] for b in r.get('buttons') or []]


def test_mdaemon_button_names_offered_product(chat):
    chat.say('Нужен MDaemon Standard')
    r = chat.say('на 20 пользователей, на год')
    names = labels(r)
    assert names and all('Standard' not in n for n in names), names
    assert any('Messaging' in n or 'MDaemon' in n for n in names), names


def test_assumed_term_is_said_out_loud(chat):
    chat.say('Нужно защитить почту и файлы на 50 сотрудников')
    chat.say(action='focus', value='all')
    chat.say('не знаю')               # непонятный ответ на вопрос о сроке
    r = chat.say(action='deployment', value='local')
    assert '12 месяцев' in r['reply'] and 'другой срок' in r['reply'], r['reply']


import pytest  # noqa: E402


@pytest.mark.parametrize('text,must,pending', [
    ('Ключ не активируется, пишет что лицензия недействительна', 'активац', True),
    ('Купили Kaspersky, не могу активировать ключ', 'активац', True),
    ('Какой статус моего заказа?', 'личном кабинете', True),
    ('Не приходит письмо с ключом после оплаты', '#q9', True),
    ('Хочу вернуть деньги за лицензию', 'возврату не подлежат', True),
    ('Как восстановить пароль от личного кабинета?', 'login.softline.ru/password', False),
    ('Нужна доверенность для получения?', 'М-2', False),
    ('Как оплатить заказ?', 'СБП', False),
    ('Сколько идёт доставка?', '2–7 рабочих дней', False),
    ('Где взять закрывающие документы по заказу?', 'edo@softline.com', False),
    ('Есть техподдержка после покупки?', '3 месяца', False),
])
def test_after_purchase_and_help_answers(chat, text, must, pending):
    r = chat.say(text)
    assert must in r['reply'], r['reply']
    assert '₽' not in r['reply'], r['reply']       # не уходим в продажу товара
    assert chat.state == 'open'
    if pending:
        chat.say('Проверил, не помогло')
        assert chat.state == 'pending'
    assert r['reply'].count('?') <= 1


@pytest.mark.parametrize('text', ['Нужен менеджер паролей Kaspersky Password Manager на 5 пользователей',
                                  'Нужна техническая поддержка Astra Linux на год, сколько стоит?',
                                  'Нужна лицензия с активацией на 10 рабочих мест Windows 11 Pro'])
def test_product_requests_not_taken_by_help_topics(chat, text):
    r = chat.say(text)
    for wrong in ('login.softline.ru', '128-41-36', 'Проблему с активацией'):
        assert wrong not in r['reply'], r['reply']


# --- КП: скидка купона и несколько позиций доходят до PDF (27.11) ---
import uuid  # noqa: E402

from eval.local import MANAGER_KEY, Chat  # noqa: E402
import support_app.documents as documents  # noqa: E402

H = {'X-Manager-Key': MANAGER_KEY}
REQ = 'ООО «Вектор», ИНН 7701234560, КПП 770101001'


def approve_and_get_pdf(client, chat, monkeypatch):
    drawn = []
    original = documents._p  # каждая надпись КП проходит через _p — собираем текст документа
    monkeypatch.setattr(documents, '_p', lambda text, style: (drawn.append(str(text)), original(text, style))[1])
    cid = client.get('/support/api/case', headers={'Authorization': 'Bearer ' + chat.token}).json()['id']
    row = next(c for c in client.get('/support/api/manager/cases?state=all&limit=100', headers=H).json()['cases'] if c['id'] == cid)
    assert row['quote'], row
    r = client.post(f'/support/api/manager/cases/{cid}/decision', headers=H,
                    json={'choice': 'approve', 'version': row['version'], 'request_id': str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()['document_url'], r.text
    pdf = client.get(r.json()['document_url'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    return row['quote'], ' '.join(drawn)


def test_coupon_discount_goes_into_quote_pdf(client, monkeypatch):
    chat = Chat(client)
    chat.say('Windows 11 Pro', page='store.softline.ru/microsoft/microsoft-windows-11-pro-380385/')
    chat.say('Нужно 2 лицензии')
    chat.say('Дайте скидку 5%')
    r = chat.say('Подготовьте КП. ' + REQ)
    assert 'со скидкой по купону 5%' in r['reply'], r['reply']
    quote, text = approve_and_get_pdf(client, chat, monkeypatch)
    assert quote['discount_percent'] == 5
    assert 'Скидка по купону 5%' in text and 'Итого со скидкой' in text, text


def test_two_products_quote_is_pdf_with_both_lines(client, monkeypatch):
    chat = Chat(client)
    chat.say('Беру один Windows 11 Pro и две лицензии Office для дома и бизнеса 2024. Дайте общий итог.')
    r = chat.say(REQ)
    assert 'Черновик КП' in r['reply'] and chat.state == 'pending', r['reply']
    quote, text = approve_and_get_pdf(client, chat, monkeypatch)
    assert len(quote['items']) == 2
    assert 'Windows 11 Pro' in text and 'Office' in text and 'Сумма по фиду' in text, text


# --- кабинет: сводка передачи и выгрузка (27.11) ---
def test_handoff_has_summary_for_manager(client):
    chat = Chat(client)
    chat.say('Нужна КриптоПро CSP 5.0 на 19 рабочих мест')
    chat.say('Нужна скидка 15%, позовите менеджера')
    assert chat.state == 'pending'
    cid = client.get('/support/api/case', headers={'Authorization': 'Bearer ' + chat.token}).json()['id']
    row = next(c for c in client.get('/support/api/manager/cases?state=all&limit=100', headers=H).json()['cases'] if c['id'] == cid)
    assert row['summary'].startswith('Причина: ') and 'Последнее от клиента' in row['summary'], row['summary']
    assert row['reason_text']


def test_cases_export_csv(client):
    chat = Chat(client)
    chat.say('=HYPERLINK("http://x") позовите менеджера')
    r = client.get('/support/api/manager/cases/export.csv', headers=H)
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/csv'), r.text[:200]
    assert 'Обращение;Состояние' in r.text
    assert ';=HYPERLINK' not in r.text and "'=HYPERLINK" in r.text
    assert client.get('/support/api/manager/cases/export.csv').status_code == 401


# --- проверка Codex 27.11, круг 3: регрессии ---
def case_row(client, chat):
    cid = client.get('/support/api/case', headers={'Authorization': 'Bearer ' + chat.token}).json()['id']
    return next(c for c in client.get('/support/api/manager/cases?state=all&limit=100', headers=H).json()['cases'] if c['id'] == cid)


def test_quote_not_replaced_while_manager_reviews(client, monkeypatch):
    chat = Chat(client)
    chat.say('Беру один Windows 11 Pro и две лицензии Office для дома и бизнеса 2024. Дайте общий итог.')
    chat.say(REQ)
    first = case_row(client, chat)
    r = chat.say('Беру один Windows 11 Pro и три лицензии Office для дома и бизнеса 2024.')
    r = chat.say(REQ)
    assert 'уже у менеджера' in r['reply'], r['reply']
    after = case_row(client, chat)
    assert after['quote']['amount_kopecks'] == first['quote']['amount_kopecks']


def test_multi_item_wrong_tier_goes_to_check(chat):
    r = chat.say('Нужно 9999 пользователей Kaspersky Endpoint Security Стандартный и 2 лицензии Office для дома и бизнеса 2024')
    assert 'Итого' not in r['reply'] or chat.state == 'pending', r['reply']


def test_discount_rounding_same_everywhere():
    from support_app.catalog import discounted
    assert discounted(10011, 5) == 9510 and discounted(10001, 5) == 9501 and discounted(0, 5) == 0


def test_quote_button_and_split_requisites_finish_multi_quote(chat):
    chat.say('Беру один Windows 11 Pro и две лицензии Office для дома и бизнеса 2024. Дайте общий итог.')
    r = chat.say('', action='quote') if 'action' in Chat.say.__code__.co_varnames else chat.say('Подготовьте КП')
    assert 'выберите позицию' not in r['reply'].lower(), r['reply']
    chat.say('ООО «Вектор», ИНН 7701234560')
    r = chat.say('КПП 770101001')
    assert 'Черновик КП' in r['reply'] and chat.state == 'pending', r['reply']


@pytest.mark.parametrize('text', ['Купил КриптоПро CSP, не активируется ключ', 'Заказ оплатил вчера. Лицензия до сих пор не пришла'])
def test_after_purchase_beats_sales_flows(chat, text):
    r = chat.say(text)
    assert chat.state == 'open' and '₽' not in r['reply'], r['reply']
    chat.say('Проверил, не помогло')
    assert chat.state == 'pending'


def test_return_question_before_purchase_keeps_sale(chat):
    r = chat.say('Хочу купить Astra Linux. Какие условия возврата?')
    assert 'возврату не подлежат' in r['reply'] and chat.state != 'pending' and 'номер заказа' not in r['reply'], r['reply']


def test_windows_login_problem_is_not_password_reset(chat):
    r = chat.say('Не могу зайти в Windows 11 после обновления')
    assert 'login.softline.ru' not in r['reply'], r['reply']


def test_feed_check_rejects_bad_date_and_lost_prices():
    from support_app.feed_update import check
    old = {'offers': 1000, 'available': 900, 'searchable': 500, 'source_date': '2026-11-26 13:45'}
    new = {'offers': 950, 'available': 1, 'searchable': 1, 'source_date': 'old-or-broken'}
    problems = check(new, old, 0.9)
    assert any('дата' in p for p in problems) and any('с ценой' in p for p in problems) and any('поиск' in p for p in problems)
    assert check({**old, 'source_date': '2026-11-20 10:00'}, old, 0.9)


def test_csv_leading_newline_formula_escaped():
    from support_app.summary import safe_cell
    assert safe_cell('\n=1+1').startswith("'") and safe_cell('  =1').startswith("'") and safe_cell('Нужен Office') == 'Нужен Office'


def test_explicit_term_clears_default_note(chat):
    chat.say('Не знаю, что нужно, но хотим защитить почту и файлы на 50 сотрудников')
    chat.say('почта на своем сервере linux, компьютеры windows')
    chat.say('а российский аналог?')
    r = chat.say('на 24 месяца')
    assert 'Срок вы не назвали' not in r['reply'], r['reply']


def test_vanished_item_asks_recheck_not_crash():
    from contextlib import closing

    from eval.local import mini_catalog
    from support_app.catalog import read_only
    from support_app.dialog import multi_quote
    state = {'g_items': [{'id': 'нет-такого', 'quantity': 1}], 'customer': 'ООО «Вектор»', 'inn': '7701234560', 'kpp': '770101001'}
    with closing(read_only(mini_catalog())) as db:
        reply, _ = multi_quote(db, state, lambda reason: f'[{reason}]')
    assert 'пересчитать' in reply and '[price_confirmation]' in reply and 'quote' not in state


# --- вторая независимая проверка (Claude) 27.11: регрессии ---
def test_comma_separated_items_all_kept(chat):
    r = chat.say('Беру Windows 11 Pro 1 шт, Office для дома и бизнеса 2024 2 шт')
    assert 'Windows 11 Pro' in r['reply'] and 'Office' in r['reply'] and 'Итого' in r['reply'], r['reply']


def test_leading_quantity_and_missing_item_named(chat):
    r = chat.say('Windows 11 Pro 1 шт и 2 Office для дома и бизнеса 2024 и 3 Абракадабра Супер Про')
    assert '× 2' in r['reply'], r['reply']
    assert 'Не смог точно определить' in r['reply'] and 'абракадабра' in r['reply'].lower(), r['reply']


def test_discount_after_multi_item_keeps_quote(client, monkeypatch):
    chat = Chat(client)
    chat.say('Беру один Windows 11 Pro и две лицензии Office для дома и бизнеса 2024. Дайте общий итог.')
    r = chat.say('скидку 5% можно?')
    assert 'со скидкой 5%' in r['reply'] and chat.state != 'pending', r['reply']
    r = chat.say(REQ)
    assert 'Черновик КП' in r['reply'] and chat.state == 'pending', r['reply']
    quote, text = approve_and_get_pdf(client, chat, monkeypatch)
    assert quote['discount_percent'] == 5 and len(quote['items']) == 2 and 'Итого со скидкой' in text


def test_order_number_after_bot_asked_is_accepted(chat):
    chat.say('Ключ не приходит после оплаты')
    assert chat.state == 'open'
    chat.say('В кабинете пусто, в спаме нет')
    assert chat.state == 'pending'
    r = chat.say('номер заказа 998877, ошибка 0x80070005')
    assert 'добавил к обращению' in r['reply'] and '₽' not in r['reply'], r['reply']


def test_mixed_activation_and_purchase_mentions_purchase(chat):
    r = chat.say('купили Kaspersky, ключ не подходит, и ещё нужен Office на 5 мест')
    assert chat.state == 'open' and 'Покупку' in r['reply'], r['reply']


@pytest.mark.parametrize('text', ['ключ активации касперского не подходит помогите', 'мы купили вчера офис и не можем его активировать',
                                  'ошибка при активации 0xC004F050', 'пишет ключ уже использован', 'ключь не падходит',
                                  'оплатил но ключа нет', 'заказ не приходит', 'верните деньги за Office'])
def test_after_purchase_variants_go_to_manager(chat, text):
    r = chat.say(text)
    assert chat.state == 'open' and '₽' not in r['reply'], (text, r['reply'])
    chat.say('Проверил, не помогло')
    assert chat.state == 'pending'


@pytest.mark.parametrize('text,must', [('можно оплатить картой?', 'карт'), ('можно ли оплатить частями', 'Отсрочки нет'),
                                       ('поддержка работает в выходные?', '128-41-36'),
                                       ('нужен пароль для входа в личный кабинет', 'login.softline.ru')])
def test_help_variants_answered(chat, text, must):
    r = chat.say(text)
    assert must in r['reply'] and '₽' not in r['reply'], (text, r['reply'])


@pytest.mark.parametrize('text', ['У меня жалоба, мне нахамили в поддержке', 'Хочу пожаловаться на ваш сервис'])
def test_complaints_recognized(chat, text):
    r = chat.say(text)
    assert chat.state == 'pending' and '₽' not in r['reply'], r['reply']


def test_customer_name_without_request_words():
    from support_app.chat import remember_quote_customer
    for text, want in (('Подготовьте КП. ООО «Вектор», ИНН 7701234560', 'ООО «Вектор»'),
                       ('КП на ООО Ромашка, ИНН 7701234560, КПП 770101001, пожалуйста срочно', 'ООО Ромашка')):
        state = {}
        remember_quote_customer(state, text)
        assert state.get('customer') == want, state


def test_discount_in_words_percent(chat):
    chat.say('Windows 11 Pro', page='store.softline.ru/microsoft/microsoft-windows-11-pro-380385/')
    r = chat.say('Хочу скидку 3 процента')
    assert '3%' in r['reply'], r['reply']


def test_complaint_reason_readable():
    from support_app.summary import reason_text
    assert reason_text('complaint') == 'Жалоба клиента' and reason_text('exact_product_request') != 'Передано менеджеру'


def test_windows_problem_goes_to_support_not_sale(chat):
    r = chat.say('Не могу зайти в Windows 11 после обновления')
    assert '128-41-36' in r['reply'] and '₽' not in r['reply'], r['reply']


def test_quantity_words_do_not_hide_product(chat):
    r = chat.say('Беру Windows 11 Pro 1 шт, Office для дома и бизнеса 2024 2 шт, Kaspersky Password Manager 3 шт')
    assert 'Windows' in r['reply'] and 'Office' in r['reply'] and 'kaspersky' in r['reply'].lower(), r['reply']
