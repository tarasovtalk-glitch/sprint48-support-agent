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
