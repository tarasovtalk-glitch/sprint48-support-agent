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


def test_invoice_request_provides_one_draft_before_manager_review(chat, client):
    chat.say('Нужно выставить счёт на 19 бессрочных лицензий КриптоПро')
    chat.say(action='placement', value='workstation')
    draft = chat.say(REQ)
    assert draft['case']['state'] == 'pending' and 'Черновик счёта' in draft['reply']
    assert draft['messages'][-1]['document_url'] == draft['document_url']
    pdf = client.get(draft['document_url'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    assert 'invoice.pdf' in pdf.headers['content-disposition']
    again = chat.say('Продублируйте, пожалуйста')
    assert not again.get('document_url')


def test_cryptopro_explicit_total_and_download_keep_quote_context(chat):
    chat.say('Сколько стоит бессрочная лицензия КриптоПро?')
    chat.say('На один компьютер, Windows')
    recalc = chat.say('А если ещё два компьютера добавить, всего 3?')
    assert '11 100 ₽' in recalc['reply']
    download = chat.say('А дистрибутив где скачать?')
    assert 'https://cryptopro.ru/products/csp' in download['reply'] and 'ИНН' not in download['reply']
    assert chat.say(REQ)['case']['state'] == 'pending'


def test_found_in_email_closes_support_exchange(chat):
    chat.say('Счёт не пришёл на почту')
    reply = chat.say('Нашёл в почте, спасибо')['reply']
    assert '?' not in reply and '₽' not in reply and 'напишите' in reply


def test_other_customer_request_is_not_searched_as_product(chat):
    reply = chat.say('Где взять реквизиты предыдущего клиента?')['reply']
    assert 'по вашему заказу' in reply and '₽' not in reply


def test_custom_cryptopro_price_is_not_accepted(chat):
    reply = chat.say('Нужно КП на бессрочный КриптоПро CSP 5.0 для компьютера по 500 ₽')['reply']
    assert 'цену из каталога' in reply and '3 700 ₽' in reply and '500 ₽' not in reply


def test_cryptopro_text_computer_and_44fz_tender(client):
    from eval.local import Chat
    c1 = Chat(client)
    c1.say('Нужен КриптоПро CSP 5.0')
    r = c1.say('бессрочную, на один компьютер, windows')
    assert '3 700 ₽' in r['reply'] and 'рабочие места или на сервер' not in r['reply']

    c2 = Chat(client)
    c2.say('Нужен КриптоПро CSP')
    r = c2.say('закупка по 44-ФЗ')
    assert c2.state == 'pending' and 'менеджер' in r['reply'].lower()


def test_post_purchase_keeps_context_and_closing_has_no_question(client):
    from eval.local import Chat
    c1 = Chat(client)
    r1 = c1.say('не могу скачать дистрибутив из кабинета, ссылка не открывается')
    assert 'браузер' in r1['reply'].lower() and c1.state == 'open'
    r2 = c1.say('другой браузер тоже не открывает')
    assert c1.state == 'pending' and 'Яндекс Браузер' not in r2['reply']

    c2 = Chat(client)
    r1 = c2.say('счёт на оплату не пришёл на почту, хотя заказ оформлен')
    assert 'спам' in r1['reply'].lower() and 'кабинет' in r1['reply'].lower()
    r2 = c2.say('в спаме нет и в кабинете пусто')
    assert c2.state == 'pending' and 'Какой продукт' not in r2['reply']

    c3 = Chat(client)
    r = c3.say('нашёл, спасибо')
    assert '?' not in r['reply']
    r = c3.say('жду ответа')
    assert '?' not in r['reply']


def test_mdaemon_standard_honest_and_quote(chat):
    r = chat.say('Нужен MDaemon Standard')
    assert 'не нашёл' in r['reply'] and 'Messaging Server' in r['reply']
    r = chat.say('на 20 пользователей, на год')
    assert 'MDaemon' in r['reply'] and r['buttons']
    assert 'Ближайшая позиция — MDaemon Messaging Server.' in r['reply']
    assert 'MDaemon Standard:' not in r['reply']
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
