"""Сценарии ТЗ, которые уже работают и показаны в видео. Любая правка обязана оставить их зелёными."""
from uuid import uuid4

from conftest import REQ
from eval.local import MANAGER_KEY


def test_cryptopro_19_workstations_quote(chat):
    r = chat.say('Нужно КП на 19 бессрочных лицензий КриптоПро')
    assert 'рабочие места или на сервер' in r['reply']
    r = chat.say(action='placement', value='workstation')
    assert '3 700 ₽' in r['reply'] and '70 300 ₽' in r['reply']
    r = chat.say(REQ)
    assert '70 300 ₽' in r['reply'] and chat.state == 'pending'


def test_mdaemon_standard_honest_and_quote(chat):
    r = chat.say('Нужен MDaemon Standard')
    assert 'не нашёл' in r['reply'] and 'Messaging Server' in r['reply']
    r = chat.say('на 20 пользователей, на год')
    assert 'MDaemon' in r['reply'] and r['buttons']
    r = chat.say(REQ)
    assert 'Черновик КП' in r['reply'] and chat.state == 'pending'


def test_needs_mail_and_files_selection(chat):
    r = chat.say('Нужно защитить почту и файлы на 50 сотрудников')
    assert 'почт' in r['reply'] and r['buttons']
    r = chat.say(action='focus', value='all')
    assert 'срок' in r['reply'].lower()
    r = chat.say(action='term', value='12')
    assert 'работать' in r['reply']
    r = chat.say(action='deployment', value='local')
    assert 'Варианты по данным каталога' in r['reply'] and '₽' in r['reply']


def test_needs_mail_and_files_requisites_make_one_quote(chat, client):
    chat.say('Не знаю, что нужно, но хотим защитить почту и файлы на 50 сотрудников')
    chat.say('Почта на своем сервере Linux, компьютеры Windows')
    selected = chat.say('А российский аналог?')
    item_ids = {button['value'] for button in selected['buttons'] if button['action'] == 'select_offer'}
    assert len(item_ids) == 2

    reply = chat.say(REQ)
    case = reply['case']
    assert case['state'] == 'pending' and 'Черновик КП' in reply['reply']
    manager = {'X-Manager-Key': MANAGER_KEY}
    cases = client.get('/support/api/manager/cases', headers=manager).json()['cases']
    quote = next(row['quote'] for row in cases if row['id'] == case['id'])
    assert {item['id'] for item in quote['items']} == item_ids
    assert sum(item['price_kopecks'] * item['quantity'] for item in quote['items']) == quote['amount_kopecks']
    approved = client.post(f'/support/api/manager/cases/{case["id"]}/decision', headers=manager, json={
        'choice': 'approve', 'version': case['version'], 'request_id': str(uuid4()),
    })
    assert approved.status_code == 200
    pdf = client.get(approved.json()['document_url'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')


def test_discount_over_5_goes_to_manager(chat):
    chat.say('Можно скидку 10%?')
    assert chat.state == 'pending'


def test_deferral_prepayment_and_coupon_5(chat):
    r = chat.say('Есть отсрочка платежа?')
    assert 'предоплата' in r['reply'] and '5%' in r['reply']
    assert chat.state == 'open'


def test_not_in_catalog_indeed_pam(chat):
    r = chat.say('Нужен Indeed PAM на 10 пользователей')
    assert 'Не нашёл Indeed PAM' in r['reply'] and chat.state == 'pending'


def test_smolensk_asks_workstation_or_server(chat):
    r = chat.say('Сколько стоит Astra Linux Смоленск?')
    assert 'рабочей станции или для сервера' in r['reply']


def test_kaspersky_edition_follow_up_keeps_vendor(chat):
    r = chat.say('Пришлите счёт на Касперского на 5 компьютеров на 1 и 2 года для сравнения')
    assert 'редакцию Kaspersky' in r['reply'] and r['case']['state'] == 'open'
    r = chat.say('Стандартный, новая лицензия')
    assert 'Kaspersky' in r['reply'] and 'Radmin' not in r['reply']


def test_cryptopro_upgrade_question_keeps_quote_open(chat):
    chat.say('КриптоПро CSP 5.0 бессрочная на 10 рабочих мест')
    r = chat.say('А на 6 версию потом обновление платное?')
    assert 'обновления зависит' in r['reply'] and 'ИНН' not in r['reply']
    assert chat.say(REQ)['case']['state'] == 'pending'


def test_redcheck_network_license_question_with_masked_inn(chat):
    r = chat.say('Чем отличается RedCheck Professional, сетевая версия, от обычной версии? ИНН [номер]')
    assert 'лицензирование по числу IP' in r['reply'] and 'ИНН' not in r['reply']


def test_explicit_operator_handoff(chat):
    chat.say('Позовите оператора')
    assert chat.state == 'pending'


def test_cryptopro_vs_vipnet_comparison(chat):
    r = chat.say('Что лучше для бухгалтерии: КриптоПро или ViPNet?')
    assert 'ViPNet CSP' in r['reply'] and 'cryptopro.ru' in r['reply']
