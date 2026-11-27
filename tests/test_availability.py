"""Наличие по правилу заказчика (брифинг 26.11, запись 3): «все товары, где есть цена, они все считаются в наличии»;
без цены («Запросить цену») — купить сейчас нельзя, только через менеджера."""
import json
import sqlite3

from support_app.catalog import import_catalog

FEED = '''<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="2026-11-26 13:45"><shop><currencies><currency id="RUR" rate="1"/></currencies>
<categories><category id="1">Антивирусы</category></categories><offers>
<offer id="1" group_id="10" available="false"><name>Антивирус Тест Цена Есть, лицензия на 1 год</name><vendor>Тест</vendor>
<vendorCode>T-1</vendorCode><url>https://store.softline.ru/t/t-1/</url><price>1000</price><currencyId>RUR</currencyId><categoryId>1</categoryId></offer>
<offer id="2" group_id="20" available="false"><name>Антивирус Тест Без Цены, лицензия на 1 год</name><vendor>Тест</vendor>
<vendorCode>T-2</vendorCode><url>https://store.softline.ru/t/t-2/</url><currencyId>RUR</currencyId><categoryId>1</categoryId></offer>
<offer id="3" group_id="30" available="true"><name>Антивирус Тест Доступен, лицензия на 1 год</name><vendor>Тест</vendor>
<vendorCode>T-3</vendorCode><url>https://store.softline.ru/t/t-3/</url><price>2000</price><currencyId>RUR</currencyId><categoryId>1</categoryId></offer>
</offers></shop></yml_catalog>'''


def test_price_means_available(tmp_path):
    feed, out = tmp_path / 'feed.yml', tmp_path / 'c.sqlite3'
    feed.write_text(FEED, encoding='utf-8')
    import_catalog(feed, out)
    db = sqlite3.connect(out)
    got = dict(db.execute('SELECT id, available FROM products'))
    assert got == {'1': 1, '2': 0, '3': 1}, got
    details = json.loads(db.execute("SELECT parameters FROM products WHERE id='1'").fetchone()[0])
    assert details['Условия поставки'] == 'Поставку подтвердит менеджер.'


def test_composition_question_stays_on_current_product(chat):
    chat.say('Хотели бы купить 5 лицензий на Майкрософт Офис для дома и бизнеса, бессрочно')
    r = chat.say('а word и excel там есть?')
    reply = r['reply']
    assert 'Spire' not in reply and '₽ ×' not in reply, reply
    assert 'Word' in reply and 'Excel' in reply, reply
    assert reply.count('?') <= 1
