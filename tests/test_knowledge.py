"""Ответ менеджера → база знаний → следующий клиент с тем же вопросом получает ответ сразу (требование заказчика:
агент пополняет базу знаний ответами менеджера). Данные клиента в базу не попадают."""
import uuid

from eval.local import MANAGER_KEY, Chat
from support_app.knowledge import keys, mask

H = {'X-Manager-Key': MANAGER_KEY}
QUESTION = 'Можно ли оплатить лицензии в рассрочку на три месяца?'
ANSWER = 'Рассрочки нет: оплата по счёту, предоплата 100 %. Для крупных заказов условия оплаты согласует менеджер.'


def case_of(client, chat):
    cid = client.get('/support/api/case', headers={'Authorization': 'Bearer ' + chat.token}).json()['id']
    row = next(c for c in client.get('/support/api/manager/cases?state=all&limit=100', headers=H).json()['cases'] if c['id'] == cid)
    return cid, row['version']


def answer_and_remember(client, text=QUESTION, note=ANSWER, remember=True):
    chat = Chat(client)
    chat.say(text)
    chat.say('Позовите менеджера')
    assert chat.state == 'pending'
    cid, version = case_of(client, chat)
    r = client.post(f'/support/api/manager/cases/{cid}/decision', headers=H,
                    json={'choice': 'approve', 'version': version, 'request_id': str(uuid.uuid4()), 'reply': note, 'remember': remember})
    assert r.status_code == 200, r.text
    return cid


def test_same_question_answered_from_manager(client):
    answer_and_remember(client)
    chat = Chat(client)
    r = chat.say('Скажите, можно оплатить лицензии в рассрочку на 3 месяца?')
    assert 'Рассрочки нет' in r['reply'] and 'менеджер' in r['reply'].lower(), r['reply']
    assert chat.state != 'pending'
    assert r['reply'].count('?') <= 1


def test_other_question_not_answered_from_knowledge(chat, client):
    answer_and_remember(client)
    r = chat.say('Сколько стоит КриптоПро CSP 5.0 бессрочная на рабочее место?')
    assert 'Рассрочки нет' not in r['reply']


def test_without_remember_nothing_saved(client):
    answer_and_remember(client, text='Есть ли у вас доставка коробочных версий в Калининград?',
                        note='Коробки в Калининград отправляем транспортной компанией.', remember=False)
    r = Chat(client).say('Доставляете коробочные версии в Калининград?')
    assert 'транспортной компанией' not in r['reply']


def test_manager_can_remember_after_decision_and_see_list(client):
    cid = answer_and_remember(client, text='Работаете ли вы с казначейскими счетами бюджетных учреждений?',
                              note='Да, работаем: укажите лицевой счёт в реквизитах.', remember=False)
    r = client.post(f'/support/api/manager/cases/{cid}/knowledge', headers=H, json={'confirmed': True})
    assert r.status_code == 200, r.text
    answers = client.get('/support/api/manager/knowledge', headers=H).json()['answers']
    assert any('лицевой счёт' in a['answer'] for a in answers)
    reply = Chat(client).say('Работаете с казначейскими счетами бюджетного учреждения?')['reply']
    assert 'лицевой счёт' in reply, reply


def test_knowledge_requires_confirmation_and_manager(client):
    cid = answer_and_remember(client, text='Можно ли получить акт сверки за прошлый квартал?', note='Акт сверки пришлём на почту.', remember=False)
    assert client.post(f'/support/api/manager/cases/{cid}/knowledge', headers=H, json={'confirmed': False}).status_code == 422
    assert client.post(f'/support/api/manager/cases/{cid}/knowledge', json={'confirmed': True}).status_code == 401


def test_personal_data_masked():
    text = 'ООО «Ромашка», ИНН 7701234560, КПП 770101001, тел. +7 (912) 345-67-89, почта ivan@romashka.ru, заказ 1234567890'
    out = mask(text)
    for leak in ('Ромашка', '7701234560', '770101001', '345-67-89', 'ivan@', '1234567890'):
        assert leak not in out, out


def test_handoff_words_are_not_question_keys():
    assert keys('Позовите менеджера, пожалуйста') == set()


# --- проверка Codex 27.11: регрессии на найденные дефекты ---
import sqlite3  # noqa: E402

import pytest  # noqa: E402

from support_app.knowledge import find_answer, has_private, question_for, save_answer  # noqa: E402
from support_app.store import SCHEMA  # noqa: E402


@pytest.fixture
def mem():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.execute('PRAGMA foreign_keys = OFF')  # источник-обращение здесь не нужен
    return db


def test_lookup_and_save_keep_transaction(mem):
    mem.execute('BEGIN IMMEDIATE')
    save_answer(mem, 'c1', QUESTION, ANSWER)
    find_answer(mem, QUESTION)
    assert mem.in_transaction
    mem.rollback()
    assert mem.execute('SELECT count(*) FROM knowledge').fetchone()[0] == 0


@pytest.mark.parametrize('other', [
    'Можно ли оплатить лицензии в рассрочку на сто месяцев?',
    'Можно ли оплатить лицензии в рассрочку на 6 месяцев?',
    'Нельзя оплатить лицензии в рассрочку на три месяца?',
])
def test_numbers_and_negation_must_match(mem, other):
    save_answer(mem, 'c1', QUESTION, ANSWER)
    assert find_answer(mem, other) is None


def test_private_answer_not_published(mem):
    for private in ('Иванов Иван Иванович, ваш заказ 12345678 отправлен на ул. Ленина 5',
                    'Позвоните Марине по номеру 912 345-67-89', 'Счёт выставлен на ООО «Ромашка», ИНН 7701234560'):
        assert has_private(private), private
        with pytest.raises(ValueError):
            save_answer(mem, 'c1', 'Когда отправите заказ с лицензиями Касперского?', private)
    assert not has_private(ANSWER)


def test_same_question_updates_not_duplicates(mem):
    for i in range(5):
        save_answer(mem, 'c1', QUESTION, ANSWER + f' Версия {i}.')
    assert mem.execute('SELECT count(*) FROM knowledge').fetchone()[0] == 1
    assert 'Версия 4' in find_answer(mem, QUESTION)['answer']


def test_broken_memory_does_not_break_chat(client):
    answer_and_remember(client)
    chat = Chat(client)
    import support_app.chat as chat_module
    original = chat_module.find_answer
    chat_module.find_answer = lambda db, text: (_ for _ in ()).throw(sqlite3.OperationalError('no such column'))
    try:
        r = chat.say(QUESTION)
    finally:
        chat_module.find_answer = original
    assert chat.last.status_code == 200 and r['reply'].strip()


def test_handoff_with_known_question_goes_to_operator(client):
    answer_and_remember(client)
    chat = Chat(client)
    chat.say('Позовите оператора: ' + QUESTION)
    assert chat.state == 'pending'


def test_quantity_change_not_intercepted(client):
    answer_and_remember(client)
    chat = Chat(client)
    chat.say('Нужна КриптоПро CSP 5.0 на 19 рабочих мест')
    r = chat.say('Сделайте на 5 рабочих мест, и можно ли оплатить лицензии в рассрочку?')
    assert 'Рассрочки нет' not in r['reply'], r['reply']


def test_question_is_customer_question_not_clarification():
    messages = [{'role': 'client', 'text': 'Есть ли у вас доставка коробочных версий в Калининград?'},
                {'role': 'bot', 'text': 'Какой продукт?'},
                {'role': 'client', 'text': 'Коробочная версия Антивируса Касперского'},
                {'role': 'client', 'text': 'Позовите менеджера'}]
    assert 'Калининград' in question_for(messages)


def test_decision_with_private_answer_still_sent_but_not_saved(client):
    chat = Chat(client)
    chat.say('Когда отправите документы по заказу лицензий?')
    chat.say('Позовите менеджера')
    cid, version = case_of(client, chat)
    r = client.post(f'/support/api/manager/cases/{cid}/decision', headers=H,
                    json={'choice': 'approve', 'version': version, 'request_id': str(uuid.uuid4()),
                          'reply': 'Иванов Иван Иванович, документы отправили на ivan@romashka.ru', 'remember': True})
    assert r.status_code == 200, r.text
    assert r.json()['knowledge']['saved'] is False
    answers = client.get('/support/api/manager/knowledge', headers=H).json()['answers']
    assert not any('ivan@' in a['answer'] or 'Иванов' in a['answer'] for a in answers)


# --- проверка Codex 27.11, круг 2 ---
@pytest.mark.parametrize('private', ['Заявка № 12345 принята, ждите письмо', 'Получатель Эльвира Кузнецова, всё отправили',
                                     'Привезём по адресу Ленина, 5 завтра', 'Ваш заказ 4521 собран'])
def test_more_private_answers_rejected(private):
    assert has_private(private), private


@pytest.mark.parametrize('general', ['Забрать коробку можно в офис продаж', 'Артикул 410137 доступен для заказа',
                                     'Оплата по счёту, предоплата 100 %.', 'Доставка электронная, ключ приходит на почту.', ANSWER])
def test_general_answers_allowed(general):
    assert not has_private(general), general


def test_negation_target_matters(mem):
    save_answer(mem, 'c1', 'Продаёте антивирус Касперского без НДС с доставкой коробки?', 'Цены с НДС; коробку доставим.')
    assert find_answer(mem, 'Продаёте антивирус Касперского без НДС с доставкой коробки?')
    assert find_answer(mem, 'Продаёте антивирус Касперского с НДС без доставки коробки?') is None


def test_year_equals_one_year(mem):
    save_answer(mem, 'c1', 'Есть ли продление антивируса на год для бюджетных учреждений?', 'Да, продление на год есть.')
    assert find_answer(mem, 'Есть ли продление антивируса на 1 год для бюджетных учреждений?')


def test_manager_word_in_question_is_not_handoff(client):
    answer_and_remember(client, text='Можно ли согласовать рассрочку через менеджера?', note='Рассрочку не согласуем, только предоплата.')
    r = Chat(client).say('Можно ли согласовать рассрочку через менеджера?')
    assert 'Рассрочку не согласуем' in r['reply'], r['reply']


def test_quantity_question_outside_deal_answered(client):
    answer_and_remember(client, text='Как получить 5 ключей после оплаты?', note='Ключи придут на почту и в личный кабинет после оплаты.')
    r = Chat(client).say('Как получить 5 ключей после оплаты?')
    assert 'личный кабинет' in r['reply'], r['reply']


def test_knowledge_failure_does_not_roll_back_decision(client, monkeypatch):
    import support_app.app as app_module
    monkeypatch.setattr(app_module, 'save_answer', lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError('no such table')))
    chat = Chat(client)
    chat.say('Можно ли оплатить картой физлица счёт для организации?')
    chat.say('Позовите менеджера')
    cid, version = case_of(client, chat)
    r = client.post(f'/support/api/manager/cases/{cid}/decision', headers=H,
                    json={'choice': 'approve', 'version': version, 'request_id': str(uuid.uuid4()),
                          'reply': 'Картой физлица можно, счёт выставим на организацию.', 'remember': True})
    assert r.status_code == 200, r.text
    assert r.json()['knowledge']['saved'] is False and r.json()['state'] == 'approved'
