"""Регрессии: баги, найденные прогоном набора из 60 диалогов (eval/nabor60.jsonl). Каждый тест — реплики клиента из набора."""
import re

from conftest import REQ

PRICE = re.compile(r'\d[\d\s ]*(?:,\d+)?\s?₽')


def test_d02_product_name_after_question_gets_price(chat):
    """Причина 1: после «какой продукт нужен?» следующая реплика — это название товара, а не новая заготовка."""
    chat.say('Добрый день, нужна цена')
    r = chat.say('КриптоАРМ Стандарт Плюс 5')
    assert PRICE.search(r['reply']), r['reply']


def test_d31_requisites_any_step_cryptopro(chat):
    """Причина 1б: «19 мест» — это рабочие места; реквизиты принимаются на любом шаге."""
    chat.say('Нужен счёт на КриптоПро CSP 5.0 бессрочная, 19 мест')
    r = chat.say(REQ)
    assert '70 300 ₽' in r['reply'] and chat.state == 'pending'


def test_no_repeated_same_question(chat):
    """Агент не задаёт один и тот же вопрос два раза подряд."""
    a = chat.say('Сколько стоит лицензия?')['reply']
    b = chat.say('Сколько стоит лицензия?')['reply']
    assert not (a.rstrip().endswith('?') and a == b)


def test_three_years_is_term_not_quantity(chat):
    r = chat.say('Kaspersky Endpoint Security для бизнеса Стандартный на 3 года')
    assert '× 3 ' not in r['reply']


def test_not_gost_excludes_gost(chat):
    r = chat.say('сколько стоит лицензия криптоарм? не гост')
    assert 'ГОСТ' not in r['reply'].split('\n')[1] if '\n' in r['reply'] else True


def test_d10_approx_price_is_not_random_product(chat):
    """«а примерно? хоть порядок цифр» не должно находить «Электронный курс … Порядок производства»."""
    chat.say('сколько стоит лицензия мультифактор, если необходимо 200')
    r = chat.say('а примерно? хоть порядок цифр')
    assert 'курс' not in r['reply'].lower()


def test_d43_followup_stays_on_product(chat):
    """Уточнение «одно подключение одновременно» остаётся про AnyDesk, а не уходит в другой товар."""
    chat.say('сколько будет стоить анидеск для одного системного администратора до 60 компьютеров')
    r = chat.say('одно подключение одновременно')
    assert 'AnyDesk' in r['reply'] or 'anydesk' in r['reply'].lower(), r['reply']


def test_d50_office365_is_not_kaspersky_for_office(chat):
    """«Kaspersky для Microsoft Office 365» — это не сам Office 365."""
    r = chat.say('есть ли возможность через вас приобрести лицензию на office 365 для организации?')
    assert 'Kaspersky' not in r['reply']


def test_d51_windows_server_not_in_catalog(chat):
    r = chat.say('возможно ли у вас приобрести операционную систему windows server 2025 standard (16 ядер)?')
    assert 'в каталоге Softline Store нет' in r['reply'] and 'менеджер' in r['reply'] and chat.state == 'pending', r['reply']


def test_d49_missing_product_goes_to_manager(chat):
    r = chat.say('можно ли купить юр лицу лицензию на adobe photoshop?')
    assert 'нет' in r['reply'] and chat.state == 'pending', r['reply']   # кик-офф 26.11: товара нет — сразу менеджеру


def test_discount_line_names_product(chat):
    """Скидка называется вместе с позицией и карточкой: видно, от какой цены считали."""
    chat.say('Windows 11 Pro', page='store.softline.ru/microsoft/microsoft-windows-11-pro-380385/')
    r = chat.say('А по купону скидка будет?')
    if 'Со скидкой' in r['reply']:
        assert 'Windows 11 Pro' in r['reply']


def test_html_entities_unescaped_in_names(chat):
    r = chat.say('Сколько стоит Windows 11 Pro?')
    assert '&quot;' not in r['reply'] and '&amp;' not in r['reply']


def test_thanks_closes_without_question(chat):
    chat.say('Сколько стоит Windows 11 Pro?')
    r = chat.say('Спасибо, всё понятно')
    assert '?' not in r['reply']


def test_order_history_goes_to_manager(chat):
    r = chat.say('В ноябре покупал лицензию Dr.Web, ключ потерялся, помогите восстановить')
    assert 'менеджер' in r['reply'] and chat.state == 'pending'


def test_compare_two_terms(chat):
    """Сравнение сроков: по позиции на каждый срок, суммы только из каталога."""
    r = chat.say('Сравните ContentReader PDF 16 Corporate 1 Standalone на один год и на три года')
    assert 'Сравнение по сроку' in r['reply'] and '1 год' in r['reply'] and '3 года' in r['reply'], r['reply']


def test_number_words_quantity(chat):
    r = chat.say('КриптоПро CSP 5.0 бессрочные на рабочее место, три штуки. Сколько суммарно?')
    assert '11 100 ₽' in r['reply'], r['reply']
    r = chat.say('Исправление: семь, а не три.')
    assert '25 900 ₽' in r['reply'], r['reply']


def test_changed_mind_perpetual_to_annual(chat):
    chat.say('Назовите цену одной бессрочной лицензии КриптоПро CSP 5.0 на рабочее место.')
    r = chat.say('Передумал, бессрочная отпадает. Теперь только годовая КриптоПро CSP 5.0 на то же рабочее место. Сколько?')
    assert '1 850 ₽' in r['reply'], r['reply']


def test_link_only_gets_price_and_question(chat):
    r = chat.say('https://store.softline.ru/kripto-pro/-410137/')
    assert '3 700 ₽' in r['reply'] and r['reply'].count('?') == 1, r['reply']


def test_off_topic_closes_politely(chat):
    r = chat.say('Продиктуйте рецепт блинов на кефире, купить ничего не хочу.')
    assert '?' not in r['reply'] and '₽' not in r['reply']


def test_missing_key_after_payment_to_manager(chat):
    chat.say('Купили электронный ключ, оплата прошла, а письма с ключом нет. Во входящих и спаме проверено.')
    assert chat.state == 'pending'


def test_tender_goes_to_manager(chat):
    r = chat.say('Нужен КриптоАРМ Стандарт Плюс 5. Закупка по 44-ФЗ, сможете заполнить форму участия?')
    assert 'менеджер' in r['reply'] and chat.state == 'pending'


def test_two_products_one_message_total_and_quote(chat):
    r = chat.say('Беру один Windows 11 Pro и две лицензии Office для дома и бизнеса 2024. Дайте общий итог.')
    assert 'Итого:' in r['reply'] and r['reply'].count('Карточка:') == 2, r['reply']
    r = chat.say(REQ)
    assert 'Черновик КП' in r['reply'] and chat.state == 'pending', r['reply']


def test_organization_name_is_not_a_product(chat):
    """«ООО «Вектор»» — покупатель; поиск не должен находить товар «Векторы»."""
    r = chat.say('ООО «Вектор», ИНН 7701234560, КПП 770101001')
    assert 'Вектор' not in r['reply'].replace('ООО «Вектор»', '') or 'Черновик' in r['reply'], r['reply']
    assert '₽' not in r['reply']


def test_missing_then_analog_from_catalog_or_manager(chat):
    """После «нет в каталоге» просьба об аналоге: товар из каталога по смыслу или менеджер, но не случайная позиция."""
    chat.say('Какая цена GitLab Unlimited на 300 пользователей self hosted в год?')
    r = chat.say('А российский аналог есть?')
    assert 'Solar' not in r['reply'] and ('GitFlic' in r['reply'] or 'менеджер' in r['reply']), r['reply']
