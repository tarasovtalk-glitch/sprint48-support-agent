"""База ответов менеджера: менеджер отметил ответ «запомнить» — следующий клиент с тем же вопросом получает его сразу.

Правила (проверка Codex 27.11):
- в общую базу идёт только общий ответ: если в ответе менеджера есть данные клиента (почта, телефон, реквизиты,
  номера, ФИО, адрес, организация), ответ остаётся в обращении и в базу не сохраняется;
- вопрос обезличивается до записи;
- совпадение — по основам смысловых слов: не меньше двух общих, доля общих (Жаккар) от 0,6, те же числа
  и то же отрицание («три месяца» ≠ «сто месяцев», «с НДС» ≠ «без НДС»);
- повтор того же вопроса обновляет ответ, а не плодит дубли;
- таблица создаётся при старте хранилища (store.SCHEMA): внутри хода схему не трогаем, чтобы не рвать транзакцию.
"""
import re

from .catalog import normalize
from .dialog import digits, stem, words

# слова просьбы позвать человека и вежливые/служебные слова не описывают сам вопрос
HANDOFF_WORDS = re.compile(r'^(?:позов|позвать|позвон|подключ|соедин|менеджер|оператор|специалист|человек|живой|ответьт|напишит|свяжит)')
FILLER_WORDS = re.compile(r'^(?:можн|нужн|подскаж|скажит|пожалуйст|хотел|хотим|хочу|интерес|вопрос|ваш|как(?:ой|ая|ие|их|ое)|есть|если|также|просто'
                          r'|здравств|добр|спасиб|очень|этот|эта|это|они|оно|него|нему|него|чтобы|будет|может)')
NAMES = ('александр|алексей|андрей|анна|антон|артём|артем|борис|вадим|валентин|валерий|василий|вера|виктор|виктория|владимир|владислав'
         '|галина|георгий|григорий|дарья|денис|дмитрий|евгений|евгения|екатерина|елена|иван|игорь|илья|ирина|кирилл|константин|ксения'
         '|лариса|леонид|людмила|максим|марина|мария|михаил|надежда|наталья|никита|николай|нина|олег|ольга|павел|пётр|петр|полина'
         '|роман|светлана|семён|семен|сергей|станислав|степан|татьяна|тимур|фёдор|федор|юлия|юрий|яна|ярослав')
PRIVATE = [
    (re.compile(r'\S+@\S+\.\w+'), '[почта]'),
    (re.compile(r'(?:\+7|\b8)?[\s\-(]*\b\d{3}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b'), '[тел]'),
    (re.compile(r'\b(?:инн|кпп|огрн\w*|бик|р/?с|к/?с)\b[\s:=№]*\d+', re.I), '[реквизит]'),
    (re.compile(r'(?:№\s*\d+|\b(?:заявк|заказ|счет|счёт|договор|обращени|накладн|трек)\w*\s+(?:№\s*)?\d{3,}|\b\d{6,}\b)', re.I), '[номер]'),
    (re.compile(r'\bадрес\w*\s*[:\-]?\s*[^.;\n]{1,60}', re.I), '[адрес]'),
    (re.compile(r'\b(?:ооо|оао|пао|зао|ао|ип|гбу|мбу|фгуп|нко)\s*(?:[«"][^»"]{1,60}[»"]|[А-ЯЁ][\w\-]+(?:\s+[А-ЯЁ][\w\-]+){0,2})', re.I),
     '[организация]'),
    (re.compile(r'\b(?:г|гор|ул|пр|просп|пер|наб|ш)\.\s*[А-ЯЁ][\wЁё\-]+(?:,?[ \t]+(?:д\.\s*)?\d+\w?)?'
                r'|\b(?:улица|проспект|переулок|набережная|шоссе)\s+[А-ЯЁ][\wЁё\-]+(?:,?[ \t]+\d+\w?)?'
                r'|\b(?:д|дом|корп|корпус|стр|кв|квартира|оф|офис)\.?\s*\d+\w?'), '[адрес]'),
    (re.compile(r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна|чна|ична|инична)\b'), '[имя]'),
    (re.compile(r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.)?|\b[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.\s*)?[А-ЯЁ][а-яё]+'), '[имя]'),
    (re.compile(r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ов|ев|ёв|ин|ын|ова|ева|ёва|ина|ына|ский|ская|цкий|цкая|ко|ук|юк|енко)\b'), '[имя]'),
    (re.compile(r'\b(?:' + NAMES + r')\b(?:\s+[А-ЯЁ][а-яё]+)?|\b[А-ЯЁ][а-яё]+(?:ов|ев|ёв|ин|ын|ова|ева|ина|ына|ский|ская)\s+(?:' + NAMES + r')\b', re.I),
     '[имя]'),
]
MIN_COMMON = 2
MIN_JACCARD = 0.6
NEGATION = re.compile(r'\b(?:не|без|нет|нельзя)\b')


def mask(text: str) -> str:
    out = text or ''
    for pattern, repl in PRIVATE:
        out = pattern.sub(repl, out)
    return re.sub(r'\s+', ' ', out).strip()


ARTICLE = re.compile(r'\b(?:артикул\w*|sku|код\s+товара|id\s+товара)\s*[:№]?\s*[\w\-]+', re.I)


def has_private(text: str) -> bool:
    """В тексте есть данные конкретного клиента — такой ответ нельзя показывать другим. Артикул товара — не личные данные."""
    plain = ARTICLE.sub('', text or '')
    return mask(plain) != re.sub(r'\s+', ' ', plain).strip()


def keys(text: str) -> set[str]:
    out = set()
    for w in words(text or ''):
        if w.isdigit() or len(w) < 4 or HANDOFF_WORDS.match(w) or FILLER_WORDS.match(w):
            continue
        out.add(stem(w)[:6])
    return out


def numbers(text: str) -> set[str]:
    """Числа вопроса; «на год» = «на 1 год», поэтому единицу не считаем."""
    return set(re.findall(r'\d+', digits(text or ''))) - {'1'}


def negated(text: str) -> set[str]:
    """Что именно отрицается: «без ндс» и «с ндс, без доставки» — разные вопросы."""
    t = normalize(text or '')
    return {stem(m.group(1))[:5] for m in re.finditer(r'\b(?:не|без|нет|нельзя)\s+(?:\w+\s+)??([а-яёa-z]{3,})', t)} | (
        {'*'} if NEGATION.search(t) else set())


def save_answer(db, case_id: str, question: str, answer: str) -> dict:
    question, answer = mask(question), (answer or '').strip()
    if not answer:
        raise ValueError('Пустой ответ не сохраняется.')
    if has_private(answer):
        raise ValueError('В ответе есть данные клиента. В базу знаний — только общий ответ без имён, телефонов, реквизитов и адресов.')
    found = sorted(keys(question))
    if len(found) < MIN_COMMON:
        raise ValueError('В вопросе слишком мало смысловых слов, чтобы узнать его в следующий раз.')
    answer = re.sub(r'\s+', ' ', answer)
    same = next((r for r in db.execute('SELECT id,question FROM knowledge') if normalize(r['question']) == normalize(question)), None)
    if same:  # тот же вопрос — обновляем ответ, дублей не плодим
        db.execute('UPDATE knowledge SET answer=?, keys=?, source_case=?, created=CURRENT_TIMESTAMP WHERE id=?',
                   (answer, ' '.join(found), case_id, same['id']))
        entry_id = same['id']
    else:
        entry_id = db.execute('INSERT INTO knowledge(question,answer,keys,source_case) VALUES (?,?,?,?)',
                              (question, answer, ' '.join(found), case_id)).lastrowid
    return {'id': entry_id, 'question': question, 'answer': answer, 'keys': found, 'source_case': case_id}


def find_answer(db, text: str) -> dict | None:
    asked = keys(text)
    if len(asked) < MIN_COMMON:
        return None
    asked_numbers, asked_negated, asked_norm = numbers(text), negated(text), normalize(mask(text))
    best, best_score = None, 0.0
    for row in db.execute('SELECT id,question,answer,keys FROM knowledge ORDER BY id DESC'):
        if numbers(row['question']) != asked_numbers or negated(row['question']) != asked_negated:
            continue
        saved = set(row['keys'].split())
        common = asked & saved
        score = len(common) / len(asked | saved)
        if asked_norm == normalize(row['question']):
            return dict(row)
        if len(common) >= MIN_COMMON and score >= MIN_JACCARD and score > best_score:
            best, best_score = dict(row), score
    return best


QUESTION_START = re.compile(r'^(?:можно|как|где|когда|сколько|есть ли|работаете|доставля|принимает|какие|какой|что|почему|зачем|чем|возможно|подскажите|скажите)\b')


def question_for(messages: list[dict]) -> str:
    """Вопрос клиента для записи: последний вопрос по сути («?» или вопросительное слово), не «позовите менеджера»
    и не уточнение на вопрос бота; если такого нет — первая содержательная реплика клиента."""
    client = [m['text'] for m in messages if m['role'] == 'client' and len(keys(m['text'])) >= MIN_COMMON]
    for text in reversed(client):
        if '?' in text or QUESTION_START.search(normalize(text)):
            return text
    return client[0] if client else ''


def all_answers(db, limit=50) -> list[dict]:
    return [dict(r) for r in db.execute('SELECT id,question,answer,source_case,created FROM knowledge ORDER BY id DESC LIMIT ?', (limit,))]


AGENT_RULES = [
    {
        'id': 'rule-discount',
        'title': 'Скидку до 5% агент даёт сам купоном, больше решает менеджер',
        'meta': 'Из условий магазина Softline Store',
    },
    {
        'id': 'rule-prepay',
        'title': 'Отсрочку и постоплату агент не обещает, передаёт менеджеру',
        'meta': 'Оплата только 100% предоплатой по оферте',
    },
    {
        'id': 'rule-price',
        'title': 'Позиции без цены («Запросить цену») и тендеры агент передаёт менеджеру',
        'meta': 'Цены берутся только из каталога Softline Store',
    },
]

BUILT_IN_ARTICLES = [
    {
        'id': 'kb-docs',
        'title': 'Закрывающие документы и ЭДО',
        'meta': 'Справка Softline Store · delivery_info/#q7',
        'text': 'По заказам юрлиц бухгалтерские документы (счёт, УПД или акт) высылают по почтовому адресу из заказа; при электронной доставке — Почтой России в течение 7 рабочих дней после отправки ключа. Через ЭДО — заявка менеджеру или на edo@softline.com с оператором и реквизитами (https://store.softline.ru/delivery_info/#q7).',
    },
    {
        'id': 'kb-delivery',
        'title': 'Сроки и доставка электронных ключей и коробок',
        'meta': 'Справка Softline Store · delivery_info/#q9',
        'text': 'Электронные лицензии приходят письмом на почту из заказа по рабочим дням с 9 до 21 МСК; срок указан в карточке товара — от 5 минут до 30 рабочих дней. Коробки и оборудование: 2–3 рабочих дня по Москве и области, 2–7 рабочих дней по России после оплаты (https://store.softline.ru/delivery_info/#q9).',
    },
    {
        'id': 'kb-payment',
        'title': 'Способы оплаты и предоплата',
        'meta': 'Справка Softline Store · delivery_info/#q5',
        'text': 'Способы оплаты: банковский платёж по счёту (юрлица и ИП), банковская карта, СБП и SberPay (физлица), подарочный сертификат; физлицам при получении коробок и оборудования — картой. Отсрочки нет, оплата заранее (https://store.softline.ru/delivery_info/#q5).',
    },
    {
        'id': 'kb-support',
        'title': 'Активация ключа и базовая техподдержка',
        'meta': 'Справка Softline Store · delivery_info/#q13',
        'text': 'Базовая техподдержка Softline бесплатна 3 месяца после покупки лицензионного ПО: +7 (495) 128-41-36, store.support@softline.com, по рабочим дням с 9 до 18 МСК (https://store.softline.ru/delivery_info/#q13).',
    },
    {
        'id': 'kb-order-status',
        'title': 'Статус заказа и личный кабинет',
        'meta': 'Справка Softline Store · delivery_info/#q2',
        'text': 'Статус заказа и данные доставки видны в личном кабинете Softline — ссылка на него есть в письме о заказе (https://store.softline.ru/delivery_info/#q2).',
    },
    {
        'id': 'kb-return',
        'title': 'Возврат и обмен лицензий и товаров',
        'meta': 'Справка Softline Store · delivery_info/#q15',
        'text': 'По правилам магазина электронные лицензии возврату не подлежат: ключ генерируется под покупателя. Коробки и оборудование можно вернуть до получения или в течение 7 дней после, если не вскрыта упаковка (https://store.softline.ru/delivery_info/#q15).',
    },
    {
        'id': 'kb-password',
        'title': 'Восстановление пароля от личного кабинета',
        'meta': 'Справка Softline Store · login.softline.ru',
        'text': 'На странице входа https://login.softline.ru нажмите «Забыли пароль?» (https://login.softline.ru/password) и укажите почту аккаунта.',
    },
    {
        'id': 'kb-m2',
        'title': 'Доверенность М-2 при получении товара',
        'meta': 'Справка Softline Store · delivery_info/#q11',
        'text': 'При получении физического товара юрлицу нужна доверенность по форме М-2 и документ, удостоверяющий личность; ИП — печать или копия свидетельства и паспорта, доверенному лицу ИП — оригинал М-2; физлицу — паспорт (https://store.softline.ru/delivery_info/#q11).',
    },
    {
        'id': 'kb-vat',
        'title': 'НДС и реквизиты для счёта юрлиц и ИП',
        'meta': 'Справка Softline Store',
        'text': 'Цены в каталоге Softline Store указаны с НДС, если в карточке не сказано иное. Для юрлица нужны название организации, ИНН и КПП; для ИП — ФИО/название и ИНН из 12 цифр (КПП не требуется).',
    },
    {
        'id': 'kb-person',
        'title': 'Покупка для физических лиц',
        'meta': 'Справка Softline Store',
        'text': 'Физическое лицо может купить ПО на сайте store.softline.ru с оплатой картой, СБП или SberPay; документы оформляются на покупателя.',
    },
    {
        'id': 'kb-dist',
        'title': 'Дистрибутивы и переход на новую версию',
        'meta': 'Справка Softline Store',
        'text': 'Дистрибутив обычно скачивается бесплатно с сайта производителя; в цену лицензии входит право использования. Переход на новую версию оформляется отдельной лицензией или обновлением.',
    },
    {
        'id': 'kb-registry',
        'title': 'Подтверждение легальности и реестр российского ПО',
        'meta': 'Справка Softline Store',
        'text': 'Юрлицу по оплаченному заказу приходят закрывающие документы (УПД или акт) с названием программы; вместе с письмом-лицензией они подтверждают законную покупку. Номер записи в едином реестре российского ПО подтверждается по карточке позиции.',
    },
]
