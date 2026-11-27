"""Сценарии ТЗ, которые уже работают и показаны в видео. Любая правка обязана оставить их зелёными."""
from conftest import REQ


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


def test_explicit_operator_handoff(chat):
    chat.say('Позовите оператора')
    assert chat.state == 'pending'


def test_cryptopro_vs_vipnet_comparison(chat):
    r = chat.say('Что лучше для бухгалтерии: КриптоПро или ViPNet?')
    assert 'ViPNet CSP' in r['reply'] and 'cryptopro.ru' in r['reply']
