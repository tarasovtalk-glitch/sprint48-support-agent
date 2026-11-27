import json
import re
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from .dialog import (
    CORRECTION, catalog_turn, digits, is_closing, multi_quote, quantity, support_topic, units_for,
)
from .catalog import discounted, find_matches, normalize, purchasable_units, read_only, view
from .documents import rubles
from .selection import Selection, selection_result
from .knowledge import find_answer
from .store import append_event


CRYPTO_WORKSTATION = '410137'
CRYPTO_NAME = re.compile(r'крипто\s*-?\s*про|crypto\s*pro|kripto\s*pro')
CRYPTO_OTHER = re.compile(r'\btsp\b|\bocsp\b|\bdss\b|\bjcp\b|\bуц\b|ipsec|криптоарм|crypto\s*arm')
NEEDS_QUERY = re.compile(r'защит.*(?:почт|файл)|(?:почт|файл).*защит')
REGISTRY_QUERY = re.compile(r'российск|отечествен|реестр')
EXPLICIT_HANDOFF = re.compile(r'позовите оператора|свяжите с менеджером|тендер|госзакупк')
TENDER = re.compile(r'\b(?:44|223)\s*[-‐‑–—]?\s*фз\b|тендер|госзакупк|\bкотировк|проект\w*\s+(?:контракт|договор)')
DEFERRED_PAYMENT = re.compile(r'оплат\w*.{0,40}через\s+\d+\s+(?:дн|месяц)|отсроч\w*\s+на\s+\d+\s+(?:дн|месяц)')
SUPPORT_TRIED = re.compile(r'не\s+(?:помог|получ)|по.?прежнему|вс[её]\s+(?:ещ[её]|равно)|до\s+сих\s+пор|\bспам\w*.{0,25}проверен')
INVOICE_REQUEST = re.compile(r'\b(?:выстав\w*|пришл\w*|сформируй\w*|нужен|хочу)\s+(?:\w+\s+){0,2}сч[её]т\b')
KASPERSKY_CENTER = re.compile(r'kaspersky\s+security\s+cent(?:er|re)|\bksc\b|(?:центр|консол\w*)\s+(?:администрирован|управлен)')
ANYDESK_NAME = re.compile(r'\b(?:anydesk|анидеск|энидеск)\w*')
TOTAL_QUANTITY = re.compile(r'\b(?:всего|итого|суммарно)\s*:?\s*([1-9]\d{0,3})(?=\s*(?:[?!.),]*$|шт|мест|компьютер|устройств))')
PRIVATE_ORDER_REQUEST = re.compile(
    r'\b(?:инн|кпп|почт\w*|телефон\w*|реквизит\w*|кп|сч[её]т)\b.{0,48}'
    r'(?:(?:чуж\w*|прошл\w*|предыдущ\w*|друг\w*)\s+(?:клиент|покупател|пользовател|заказ)|клиент\w*\s+до\s+меня)'
    r'|\bчуж\w*\s+(?:кп|сч[её]т|реквизит\w*|заказ\w*)\b'
)
CUSTOM_UNIT_PRICE = re.compile(r'\b(?:по|за)\s+\d[\d \u00a0]*(?:[.,]\d{1,2})?\s*(?:₽|руб\w*|р\.)')
MDAEMON_NAME = re.compile(r'mdaemon|м\s*деймон')
MDAEMON_STANDARD = re.compile(r'\bstandard\b|\bстандарт\w*')
SMOLENSK = re.compile(r'(?:linux|линукс).{0,35}смоленск|смоленск.{0,35}(?:linux|линукс)')
WINDOWS_PRO = re.compile(r'\bwindows\s+11\s+pro\b')
OFFICE_HOME = re.compile(r'\b(?:дома|для дома|домашн\w*)\b.{0,40}\b(?:office|офис)\b|\b(?:office|офис)\b.{0,40}\bдля дома\b')
EDUCATIONAL_PRICE = re.compile(r'школ|учебн|образовательн')
VIPNET_NAME = re.compile(r'vipnet|випнет')
CSP_COMPARISON = (
    'КриптоПро CSP и ViPNet CSP поддерживают создание и проверку электронной подписи. '
    'Для бухгалтерии выбирайте криптопровайдер, который прямо поддерживает ваш сервис отчётности '
    'для вашей ОС и носителя ключа. Если в требованиях указан КриптоПро CSP, выбирайте его. '
    'Если сервис поддерживает оба, сравните условия лицензии и совместимость с тем, что уже установлено.\n'
    'Источники: https://cryptopro.ru/products/csp и https://www.infotecs.ru/products/vipnet-csp/\n'
    'В каком сервисе вы сдаёте отчётность?'
)
TEXT_TERMS = (
    (12, re.compile(r'\b12\s*месяц|\bна\s+(?:1\s+год|один\s+год|год)(?:\s|$|[,.!?])')),
    (24, re.compile(r'\b24\s*месяц|\bна\s+(?:2|два)\s+год')),
)
LOCAL_DEPLOYMENT = re.compile(r'\b(?:свое?м|своих?|нашем|наших|собственном|собственных)\s+сервер|\bлокальн\w+')
CLOUD_DEPLOYMENT = re.compile(r'^\s*облако[.!]?\s*$|\bв\s+облак|\bоблачн\w+\s+(?:развертыван|верси|решен)')
REGISTRY_REFERENCES = (
    ('kaspersky security для почтовых серверов базовая лицензия', '203'),
    ('kaspersky endpoint security для бизнеса стандартный базовая лицензия', '205'),
    ('kaspersky total security для бизнеса базовая лицензия', '204'),
)
REGISTRY_SOURCE = 'https://reestr.digital.gov.ru/reestr/?EX_PAGE_N=12&EX_PAGE_S=100&PAGE_N=304&PAGE_S=100'
WORKPLACE_CHOICES = [('Рабочие места', 'placement', 'workstation'), ('Сервер', 'placement', 'server')]
JOIN_MANAGER = [('Позвать оператора', 'handoff', '')]
QUOTE_CUSTOMER_PROMPT = 'Для КП укажите название организации, ИНН и КПП.'
QUOTE_REQUISITES = re.compile(r'\b(ИНН|КПП)\b[\s:=№]*([0-9][A-Za-z0-9]*)', re.I)
INN_FORMAT = re.compile(r'(?:[0-9]{10}|[0-9]{12})')
INN_CONFIRM = re.compile(r'^\s*(?:да|ага|верно|все\s+верно|правильно|подтверждаю|инн\s+верн\w*|верный|формируйте)(?![^\W_])')
KPP_FORMAT = re.compile(r'[0-9]{4}[A-Za-z0-9]{2}[0-9]{3}')
BUTTON_TEXT = {
    ('placement', 'workstation'): 'На рабочие места', ('placement', 'server'): 'На сервер',
    ('term', '12'): 'На 12 месяцев', ('term', '24'): 'На 24 месяца',
    ('deployment', 'local'): 'На своих серверах', ('deployment', 'cloud'): 'В облаке',
    ('deployment', 'flexible'): 'Рассмотрю оба варианта', ('focus', 'mail'): 'Сначала защита почты',
    ('focus', 'all'): 'И почта, и файлы',
}
PRODUCT_WORDS = re.compile(r'[^\W_]+', re.UNICODE)
PURCHASE_WORDS = re.compile(r'цен|стоим|приобрест|\bкп\b|хочу купить|сколько стоит|подбира')
KNOWN_WORDS = {'на', 'по', 'для', 'и', 'за', 'или', 'как', 'подскажите', 'скажите', 'пожалуйста', 'хочу', 'нужна', 'нужно',
               'нужен', 'купить', 'цены', 'цену', 'цена', 'стоимость', 'сколько', 'стоит', 'лицензия', 'лицензии', 'кп',
               'инн', 'ооо', 'продукт', 'добрый', 'день', 'привет', 'здравствуйте', 'какие', 'есть', 'можно', 'да', 'нет'}
INTENT_CUES = {
    'помоги', 'помогите', 'выбрать', 'подбор', 'подберите', 'нужна', 'нужен', 'нужно', 'цена', 'цену', 'стоимость',
    'сколько', 'стоит', 'счет', 'оплата', 'заказ', 'купить', 'покупка', 'поддержка', 'документы', 'программа', 'программу',
    'лицензия', 'лицензию', 'лицензий', 'оформить', 'сравнить', 'сравнение', 'варианты', 'решение', 'кп',
}


def intent_cues(text: str) -> str:
    query = normalize(text)
    if TENDER.search(query) or DEFERRED_PAYMENT.search(query) or PRIVATE_ORDER_REQUEST.search(query):
        return ''
    if CRYPTO_NAME.search(query) or MDAEMON_NAME.search(query) or re.search(r'защит.*(?:почт|файл)|закрывающ|отсроч|оператор|купон|скидк', query):
        return ''
    tokens = [w for w in PRODUCT_WORDS.findall(query) if w in INTENT_CUES]
    return ' '.join(tokens[:20]) if len(tokens) >= 2 else ''


def tool_request(text: str, action: str | None, value: str, state: dict):
    """Return only scenario facts suitable for the model, never the customer's raw input."""
    query = normalize(text)
    if (TENDER.search(query) or DEFERRED_PAYMENT.search(query) or PRIVATE_ORDER_REQUEST.search(query)
            or (state.get('post_purchase') and is_closing(text))):
        return None
    if state.get('flow') == 'smolensk' and EDUCATIONAL_PRICE.search(query) and not state.get('smolensk_academic'):
        return ('Клиент уточняет условия для школы по ранее названной редакции. Подтверждённой цены для школы нет.',
                ('contact_manager',))
    if state.get('flow') == 'needs':
        if REGISTRY_QUERY.search(query) and state.get('term') and state.get('deployment'):
            return ('Клиент спрашивает, есть ли российский аналог и запись в реестре отечественного ПО. Требования уже собраны.',
                    ('check_registry', 'search_catalog'))
        if action == 'deployment' and value in {'local', 'cloud', 'flexible'} and state.get('term') and state.get('quantity'):
            return ('Клиент выбрал размещение. Задача, срок лицензии и количество уже известны. Можно искать в каталоге.',
                    ('search_catalog', 'clarify_requirements'))
        if (action == 'select_offer' and value in state.get('offered_ids', [])) or (state.get('awaiting_customer') and text):
            return ('Клиент выбрал позицию или заполняет реквизиты для черновика КП. Нужно подготовить КП для менеджера; недостающие поля уточнит система.',
                    ('draft_quote', 'clarify_requirements'))
    if NEEDS_QUERY.search(query):
        return ('Клиенту нужно ПО для защиты почты или файлов. Срок и размещение ещё не подтверждены. Сначала нужно уточнить требования.',
                ('clarify_requirements', 'search_catalog'))
    if action == 'handoff' or (not state.get('awaiting_customer') and EXPLICIT_HANDOFF.search(query)):
        return ('Клиент просит подключить оператора или требует согласования менеджера. Нужна передача оператору.',
                ('contact_manager', 'clarify_requirements'))
    return None


def chat_price(kopecks: int) -> str:
    amount = rubles(kopecks).removesuffix(' руб.').removesuffix(',00')
    return f'{amount} ₽'


def buttons(items):
    return [{'label': label, 'action': action, 'value': value} for label, action, value in items]


def customer_text(text, action, value):
    return text or BUTTON_TEXT.get((action, value), {
        'select_offer': 'Выбрана позиция каталога', 'quote': 'Запросить коммерческое предложение',
        'handoff': 'Позвать оператора', 'deferral': 'Есть ли отсрочка?',
        'more_discount': 'Нужна скидка больше 5%', 'price': 'Какая цена?', 'invoice': 'Нужен счёт',
    }.get(action, 'Уточнение по подбору'))


def lookup(catalog: Path, offer_id: str):
    if not catalog.is_file():
        return None
    with closing(read_only(catalog)) as db:
        row = db.execute('SELECT * FROM products WHERE id=?', (offer_id,)).fetchone()
        if row is None:
            return None
        date = db.execute("SELECT value FROM metadata WHERE name='source_date'").fetchone()
        return {**view(row), 'source_date': date['value'] if date else ''}


def offer_id_from_url(raw: str) -> str | None:
    try:
        candidate = urlsplit(raw if '://' in raw else 'https://' + raw)
    except ValueError:
        return None
    if candidate.scheme != 'https' or candidate.netloc.lower() != 'store.softline.ru':
        return None
    match = re.search(r'-(\d+)/?$', candidate.path)
    return match.group(1) if match else None


def resolve_product(catalog: Path, text: str, quantity: int | None, page_url: str = ''):
    if not catalog.is_file():
        return []
    explicit_urls = re.findall(r'https?://store\.softline\.ru/[^\s<>\]\)]+', text, re.I)
    page_sources = [page_url] if PURCHASE_WORDS.search(normalize(text)) else []
    for url in [*explicit_urls, *page_sources]:
        offer_id = offer_id_from_url(url)
        if offer_id:
            found = lookup(catalog, offer_id)
            if found:
                return [found]
    query = normalize(text)
    card_id = '380385' if WINDOWS_PRO.search(query) else '473568' if OFFICE_HOME.search(query) else None
    if card_id:
        card = lookup(catalog, card_id)
        return [card] if card else []
    sku_tokens = [t for t in re.findall(r'\b[A-Z][A-Z0-9_.-]{4,29}\b', text) if any(c.isdigit() for c in t)][:3]
    phrases = re.findall(r'[«"]([^»"\r\n]{4,65})[»"]', text)[:3]
    if not phrases and PURCHASE_WORDS.search(normalize(text)):
        normal = normalize(text).split('[', 1)[0].strip()
        phrases = [normal[:85]]
    if not (sku_tokens or phrases):
        return []
    with closing(read_only(catalog)) as db:
        for sku in sku_tokens:
            row = db.execute('SELECT * FROM products WHERE sku=? ORDER BY available DESC LIMIT 1', (sku,)).fetchone()
            if row:
                return [view(row)]
        for phrase in phrases:
            words = [w for w in PRODUCT_WORDS.findall(normalize(phrase)) if len(w) >= 3 and w not in KNOWN_WORDS]
            if len(words) < 2 or len(words) > 6:
                continue
            rows = find_matches(db, words, quantity, None, active_only=True)
            exact = [option for option in rows if all(w in normalize(option['name']) for w in words)]
            if exact:
                return exact[:3]
    return []


def enter_queue(db, row, state, reason: str) -> str:
    if row['state'] == 'pending':
        return 'Запрос уже у менеджера. Его ответ появится здесь.'
    state['queue_reason'] = reason
    if reason == 'quote_review':   # менеджер одобряет ровно то, что ушло ему; правки клиента после этого его не подменяют
        state['quote_frozen'] = json.loads(json.dumps(state.get('quote')))
    db.execute("UPDATE cases SET state='pending',version=version+1,payment_due=NULL WHERE id=?", (row['id'],))
    append_event(db, row['id'], 'sent_to_manager', reason)
    return 'Передал запрос менеджеру. Его ответ появится в этом чате.'


def inn_valid(inn: str) -> bool:
    """Контрольные цифры ИНН (10 цифр — организация, 12 — ИП и физлицо)."""
    d = [int(c) for c in inn]
    check = lambda weights, n: sum(w * x for w, x in zip(weights, d)) % 11 % 10 == d[n]  # noqa: E731
    if len(d) == 10:
        return check([2, 4, 10, 3, 5, 9, 4, 6, 8], 9)
    return len(d) == 12 and check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8], 10) and check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8], 11)


def accept_inn(state, value: str):
    """ИНН с ошибкой в контрольной цифре не принимаем молча: переспрашиваем один раз; повтор того же — принимаем, менеджер проверит."""
    repeated = state.get('inn_rejected') == value and state.get('inn_rejected_turn') != state.get('turn_no')
    if inn_valid(value) or repeated:
        state['inn'] = value
        if not inn_valid(value):
            state['inn_unverified'] = True
        state.pop('inn_rejected', None)
    else:
        state.pop('inn', None)
        if state.get('inn_rejected') != value:
            state['inn_rejected_turn'] = state.get('turn_no')
        state['inn_rejected'] = value


ORDER_DETAILS = re.compile(r'\d{4,}|заказ|ошибк|0x[0-9a-f]+|скрин|снимок')
EXTRA_PURCHASE = re.compile(r'(?:ещё|еще|также|плюс|кроме\s+того)\s+(?:\w+\s+)?(?:нуж[еа]?н|надо|хочу|купить|возьм|беру)|\bи\s+(?:ещё\s+|еще\s+)?(?:нуж[еа]?н|купить)\w*\s+\w+')
ORG_FORM = re.compile(r'(?<![^\W_])(?:ООО|АО|ПАО|ЗАО|ОАО|ИП|ГБУ|МБУ|ФГБУ|ГКУ|МКУ|НКО|АНО)\s+(?:[«"][^»"]{1,60}[»"]|[^,.;\n]{2,60})')


def remember_quote_customer(state, text: str):
    for field, value in QUOTE_REQUISITES.findall(text):
        if field.upper() == 'ИНН' and INN_FORMAT.fullmatch(value):
            accept_inn(state, value)
        if field.upper() == 'КПП' and KPP_FORMAT.fullmatch(value):
            state['kpp'] = value.upper()
    name = QUOTE_REQUISITES.sub(' ', text).strip(' \t\r\n,:;.-')
    if name == text.strip(' \t\r\n,:;.-'):
        if KPP_FORMAT.fullmatch(name):
            state['kpp'] = name.upper()
            return
        bare_inn = re.search(r'(?<!\w)([0-9]{10}|[0-9]{12})(?!\w)', name)
        if bare_inn:
            accept_inn(state, bare_inn[1])
            name = (name[:bare_inn.start()] + name[bare_inn.end():]).strip(' \t\r\n,:;.-')
    name = re.sub(r'^(?:название(?: организации)?|организация|компания)\s*:\s*', '', name, flags=re.I)
    form = ORG_FORM.search(name)
    if form:   # «Подготовьте КП. ООО «Вектор»» → в КП только «ООО «Вектор»», без просьбы вокруг
        name = form.group(0).strip(' ,.;')
    if any(char.isalpha() for char in name) and not re.search(r'\b(?:инн|кпп)\b', name, re.I):
        state['customer'] = ' '.join(name.split())[:100]
    else:
        # реквизиты внутри длинной реплики: «… ИП Петров, ИНН …» — берём форму и название
        org = re.search(r'(?<![^\W_])(?:ООО|АО|ПАО|ЗАО|ОАО|ИП|ГБУ|МБУ|ФГБУ|ГКУ|МКУ|НКО|АНО)\s+[«"]?[^,.;\n]{2,60}', text)
        if org and not re.search(r'\b(?:инн|кпп)\b', org.group(0), re.I):
            state['customer'] = ' '.join(org.group(0).split())[:100]


def queue_quote(db, row, state, catalog: Path):
    if row['state'] == 'pending':
        return 'Запрос уже у менеджера. Его ответ появится здесь.', []
    if state.get('g_items') and catalog.is_file():   # расчёт нескольких позиций → КП на все строки
        with closing(read_only(catalog)) as cat:
            return multi_quote(cat, state, lambda reason: enter_queue(db, row, state, reason))
    if not state.get('offer_id'):
        return 'Сначала выберите позицию каталога, для которой нужно КП.', []
    if not state.get('quantity'):
        return 'На сколько лицензий подготовить КП?', []
    if not state.get('inn') and state.get('inn_rejected'):
        state['awaiting_customer'] = True
        return (f'ИНН {state["inn_rejected"]} не проходит проверку контрольной цифры. Проверьте, пожалуйста, нет ли опечатки? '
                'Если ИНН верный, пришлите его ещё раз — передам менеджеру на проверку.'), []
    sole_trader = len(state.get('inn') or '') == 12  # ИП: ИНН из 12 цифр, КПП у ИП нет
    missing = [label for key, label in (('customer', 'название организации'), ('inn', 'ИНН'), ('kpp', 'КПП'))
               if not state.get(key) and not (key == 'kpp' and sole_trader)]
    if missing:
        state['awaiting_customer'] = True
        return (QUOTE_CUSTOMER_PROMPT if len(missing) == 3 else f'Для КП укажите ещё {", ".join(missing)}.'), []
    if row['state'] == 'pending':
        return 'Запрос уже у менеджера. Его ответ появится здесь.', []
    product = lookup(catalog, state['offer_id'])
    if not product or not product['available'] or product['price_kopecks'] is None:
        return enter_queue(db, row, state, 'price_confirmation'), []
    requested_users = state['quantity']
    quantity = purchasable_units(product, requested_users)
    if quantity is None and state.get('g_family'):
        quantity = units_for(product, requested_users)
    if quantity is None:
        return 'Количество и цену для выбранной лицензии нужно сверить. ' + enter_queue(db, row, state, 'price_confirmation'), []
    state['quote'] = {
        'offer': product, 'quantity': quantity, 'customer': state['customer'], 'inn': state['inn'], 'kpp': state.get('kpp') or '',
        'requested_users': requested_users,
        'amount_kopecks': product['price_kopecks'] * quantity, 'vat_kopecks': None,
        'vat_status': 'НДС уточняется менеджером', 'payment_terms': 'Предоплата по оферте',
        'source_date': product['source_date'],
    }
    discount = coupon(state)
    if discount:
        state['quote']['discount_percent'] = discount
        state['quote']['amount_after_discount_kopecks'] = discounted(state['quote']['amount_kopecks'], discount)
    state['awaiting_customer'] = False
    append_event(db, row['id'], 'quote_amount_calculated', str(state['quote']['amount_kopecks']))
    message = enter_queue(db, row, state, 'quote_review')
    units = f'{chat_price(product["price_kopecks"])} × {quantity} = ' if quantity > 1 else ''
    after = (f', со скидкой по купону {discount}% — {chat_price(state["quote"]["amount_after_discount_kopecks"])}' if discount else '')
    return (f'Черновик КП готов: {product["name"]}, {units}{chat_price(state["quote"]["amount_kopecks"])} по каталогу{after}. '
            f'Сумма по каталогу проверена. {message}'), []


def coupon(state) -> int:
    """Купон, который бот уже предложил в этом диалоге (не больше 5 %): он же попадает в КП."""
    try:
        percent = int(float(str(state.get('coupon_percent') or 0).replace(',', '.')))
    except ValueError:
        return 0
    return percent if 0 < percent <= 5 else 0


def registry_selection(db, req):
    regular = selection_result(db, req.model_copy(update={'require_registry': False}))
    matches = []
    for group in regular['groups']:
        options = []
        for offer in group['offers']:
            public_entry = next((number for family, number in REGISTRY_REFERENCES
                                 if family in normalize(offer['name'])), None)
            if offer['registry'] or public_entry:
                number, source = (public_entry, REGISTRY_SOURCE) if public_entry else (offer['registry'], '')
                options.append({**offer, 'registry': number, 'registry_source': source})
        if options:
            matches.append({**group, 'offers': options})
    return matches


def next_clarify_field(state: dict) -> str:
    if state.get('flow') == 'needs' and not state.get('focus') and not state.get('focus_asked'):
        return 'focus'
    if state.get('flow') == 'mdaemon' and not state.get('quantity'):
        return 'users'
    if not state.get('term') and not state.get('term_asked'):
        return 'term'
    if not state.get('deployment') and not state.get('deployment_asked') and state.get('flow') != 'mdaemon':
        return 'deployment'
    if not state.get('quantity'):
        return 'users'
    return ''


def collect_selection(state, catalog: Path, db, case_id: str, registry=False):
    if not catalog.is_file():
        return 'Каталог ещё недоступен. Могу позвать оператора.', JOIN_MANAGER
    if state['flow'] == 'needs':
        if not state.get('focus') and state.get('focus_asked'):
            state['focus'] = 'all'
        if not state.get('focus'):
            state['focus_asked'] = True
            return 'Выбираем защиту для почты и файлов вместе или начинаем с почты?', [('И почта, и файлы', 'focus', 'all'), ('Сначала почта', 'focus', 'mail')]
    if state['flow'] == 'mdaemon' and not state.get('quantity'):
        edition = 'Редакцию MDaemon Standard в фиде не нашёл. Могу проверить MDaemon Messaging Server. ' if state.get('standard_requested') else ''
        return edition + 'На сколько пользователей нужна лицензия?', []
    if not state.get('term') and state.get('term_asked'):
        state['term'] = 12
        state['term_assumed'] = True   # клиент срок не назвал — говорим об этом прямо в ответе с вариантами
    if not state.get('term'):
        state['term_asked'] = True
        return 'На какой срок нужна лицензия?', [('12 месяцев', 'term', '12'), ('24 месяца', 'term', '24')]
    if not state.get('deployment') and state.get('deployment_asked'):
        state['deployment'] = 'flexible'
    if not state.get('deployment') and state['flow'] != 'mdaemon':
        state['deployment_asked'] = True
        return 'Где будет работать решение?', [('Свои серверы', 'deployment', 'local'), ('Облако', 'deployment', 'cloud'), ('Оба варианта', 'deployment', 'flexible')]
    if not state.get('quantity'):
        return 'Сколько пользователей или устройств нужно покрыть?', []
    query = 'защита почты' if state.get('focus') == 'mail' else state['query']
    req = Selection(mode='known' if state['flow'] == 'mdaemon' else 'needs',
                    query=query, product='MDaemon Standard' if state['flow'] == 'mdaemon' else '',
                    users=state['quantity'], term_months=state['term'], deployment=state.get('deployment', 'flexible'), require_registry=registry)
    append_event(db, case_id, 'registry_lookup' if registry else 'catalog_search', req.mode)
    with closing(read_only(catalog)) as catalog_db:
        result = selection_result(catalog_db, req)
        if registry:
            enriched = {g['topic']: g for g in result['groups']}
            for group in registry_selection(catalog_db, req):
                enriched.setdefault(group['topic'], group)
            result['groups'] = list(enriched.values())
    shown = [(group, offer) for group in result['groups'] for offer in group['offers'][:1]]
    state.pop('needs_quote_items', None)
    if not shown:
        state.pop('offered_ids', None)
        return ('По фиду не нашёл подходящий вариант с подтверждённой записью в реестре.' if registry else 'По этим требованиям точного варианта в выдаче нет.') + ' Могу позвать оператора.', JOIN_MANAGER
    state['offered_ids'] = [offer['id'] for _, offer in shown]
    lines = ['Варианты по данным каталога.' + (' Все варианты есть в реестре отечественного ПО, совместимость с вашими требованиями нужно проверить.' if registry else '')]
    if state['flow'] == 'mdaemon' and not shown[0][0]['exact_terms_found']:
        lines.append('Редакции MDaemon Standard в каталоге нет. Ближайшая позиция — MDaemon Messaging Server.')
    if state.get('term_assumed'):
        lines.append('Срок вы не назвали — показываю на 12 месяцев; нужен другой срок — напишите.')
    quote_items = []
    for group, offer in shown:
        title = offer['name'] if state['flow'] == 'mdaemon' else f'{group["topic"]}: {offer["name"]}'
        price = chat_price(offer['price_kopecks']) if offer['price_kopecks'] is not None else 'цену уточнит менеджер'
        registry_text = f', реестр № {offer["registry"]}' if registry and offer.get('registry') else ''
        units = purchasable_units(offer, state['quantity'])
        total = f' × {units} = {chat_price(offer["price_kopecks"] * units)}' if units and units > 1 and offer['price_kopecks'] else ''
        lines += ['', title, f'{price}{total}{registry_text}']
        if offer.get('url'):
            lines.append(f'Карточка: {offer["url"]}')
        if note := (offer.get('parameters') or {}).get('Условия поставки'):
            lines.append(note)
        if units and offer['available'] and offer['price_kopecks']:
            quote_items.append({'id': offer['id'], 'quantity': state['quantity'], 'units': units})
    if state['flow'] == 'needs' and len(quote_items) == len(shown):
        state['needs_quote_items'] = quote_items
        lines += ['', 'Для одного КП на все позиции пришлите название организации, ИНН и КПП.']
    # на кнопке — название того, что выбирает клиент, а не тема запроса («MDaemon Standard» вёл к Messaging Server)
    def label(topic, offer):
        name = normalize(offer['name'])
        return topic if all(w[:4] in name for w in normalize(topic).split()) else offer['name'][:45]
    return '\n'.join(lines), [('Выбрать: ' + label(group['topic'], offer), 'select_offer', offer['id']) for group, offer in shown]


# просьба позвать человека; «согласовать через менеджера» — это вопрос, а не просьба
HANDOFF_ASK = re.compile(r'(?:позов|позвать|подключ|соедин|переключ|свяж|дайте|нужен|нужна|хочу|можно|пригласит)\w*\s+(?:меня\s+)?(?:с\s+)?(?:живым\s+|живого\s+)?'
                         r'(?:оператор|менеджер|специалист|человек)|^(?:оператор|менеджер|специалист|человек)\w*\W*$')


def knowledge_hit(db, row, state, text, query, count, action, tool):
    """Ответ из базы знаний — только на вопрос без действия по сделке: не просьба об операторе, не количество,
    не реквизиты, не ответ на вопрос бота. Сбой памяти не ломает разговор: пишем событие и идём обычным путём."""
    in_deal = any(state.get(k) for k in ('flow', 'offer_id', 'g_family', 'g_items', 'quote'))
    if (not text or action or tool or (count and in_deal) or state.get('awaiting_customer') or EXPLICIT_HANDOFF.search(query)
            or HANDOFF_ASK.search(query) or QUOTE_REQUISITES.search(text) or INN_FORMAT.search(text)):
        return None
    try:
        known = find_answer(db, text)
    except sqlite3.Error as error:
        append_event(db, row['id'], 'knowledge_error', type(error).__name__)
        return None
    if known:
        append_event(db, row['id'], 'knowledge_answer', str(known['id']))
    return known


def run_turn(db, row, state, catalog: Path, *, text='', action=None, value='', intent_hint='unknown', page_url='', tool=None):
    query = normalize(text)
    if state.get('redcheck_follow_up') and re.match(r'^(?:нужн\w*\s+)?сетев\w*\s+на\s+\d+\s+ip\b', query):
        text = 'RedCheck Professional ' + text
        query = normalize(text)
        state.pop('redcheck_follow_up', None)
    state['turn_no'] = state.get('turn_no', 0) + 1
    if text is not None and not text.strip() and not action:
        return 'Напишите, пожалуйста, ваш вопрос: какой продукт нужен или что подсказать по заказу?', []
    if PRIVATE_ORDER_REQUEST.search(query):
        return 'Документы и реквизиты по вашему заказу доступны в личном кабинете. С проверкой своего заказа поможет оператор.', JOIN_MANAGER
    if TENDER.search(query):
        return 'Закупку по тендеру или 44/223-ФЗ оформляет менеджер. ' + enter_queue(db, row, state, 'tender'), []
    if DEFERRED_PAYMENT.search(query):
        return 'По оферте действует предоплата. Индивидуальные условия может согласовать менеджер. ' + enter_queue(db, row, state, 'payment_question'), []
    if row['state'] == 'pending' and re.search(r'скольк\w*\s+ждать|когда\s+ответ|срок\w*\s+(?:под\s+заказ|поставки)|\bжд[её]м\s+кп\b', query):
        return 'Запрос уже у менеджера. Он уточнит условия и срок поставки и ответит в этом чате.', []
    if state.get('post_purchase') and is_closing(text):
        return ('Менеджер ответит здесь, когда проверит обращение.' if row['state'] == 'pending'
                else 'Хорошо. Если понадобится помощь по заказу, напишите.'), []
    count_query = digits(query)
    correction = CORRECTION.search(count_query)
    total_quantity = TOTAL_QUANTITY.search(count_query) if state.get('flow') == 'cryptopro' else None
    count = total_quantity or correction or re.search(r'\b([1-9]\d{0,3})\s*(?:бессрочн\w*\s+)?(?:лицензи|сотрудник|пользовател|человек|рабочих\s+мест|раб\.?\s*мест|узл|ящик|мест|штук|шт\b)', count_query)
    previous_quantity = state.get('quantity')
    if count:
        state['quantity'] = int(count.group(1))
    elif text and quantity(text):
        state['quantity'] = quantity(text)
        count = True
    if (count and previous_quantity and state['quantity'] != previous_quantity and state.get('flow') == 'cryptopro'
            and state.get('offer_id') and row['state'] != 'pending'):
        product = lookup(catalog, state['offer_id'])
        if product and product['available'] and product['price_kopecks']:
            remember_quote_customer(state, text)
            if state.get('customer') and state.get('inn') and (state.get('kpp') or len(state['inn']) == 12):
                return queue_quote(db, row, state, catalog)
            state['awaiting_customer'] = True
            amount = product['price_kopecks'] * state['quantity']
            return (f'Пересчитал: {product["name"]} — {chat_price(product["price_kopecks"])} × {state["quantity"]} = {chat_price(amount)}. '
                    + QUOTE_CUSTOMER_PROMPT), [('Подготовить КП', 'quote', '')]
    if state.get('flow') == 'smolensk' and EDUCATIONAL_PRICE.search(query):
        offer = lookup(catalog, state['smolensk_academic']) if state.get('smolensk_academic') else None
        if offer and offer['available'] and offer['price_kopecks']:
            return (f'Для школы есть академическая позиция Astra Linux «Смоленск» для рабочей станции — '
                    f'{chat_price(offer["price_kopecks"])} за лицензию. Карточка: {offer["url"]}. '
                    'Право на академическую поставку и условия подтвердит менеджер.'), JOIN_MANAGER
        if tool == 'contact_manager':
            append_event(db, row['id'], 'model_tool_executed', tool)
        return 'Для школы цену нужно уточнить по условиям образовательной поставки. ' + enter_queue(db, row, state, 'price_confirmation'), []
    if tool == 'contact_manager':
        append_event(db, row['id'], 'model_tool_executed', tool)
        reason = state.get('post_purchase_reason', 'customer_request') if action == 'handoff' or EXPLICIT_HANDOFF.search(query) else 'model_routing'
        return enter_queue(db, row, state, reason), []
    if action == 'handoff' or re.search(r'(?:позови|подключи|соедини)\w*\s+(?:с\s+)?(?:оператор|менеджер)', query):
        return enter_queue(db, row, state, 'customer_request'), []
    known = knowledge_hit(db, row, state, text, query, count, action, tool)
    if known:  # менеджер уже отвечал на такой вопрос и сохранил общий ответ в базу знаний
        return ('Менеджер уже отвечал на такой вопрос: ' + known['answer'].rstrip()
                + '\nЕсли у вас другой случай, нажмите «Позвать оператора» — передам вопрос менеджеру.'), JOIN_MANAGER
    if (row['state'] == 'pending' and text and state.get('queue_reason') in ('order_question', 'activation_problem', 'payment_question', 'closing_documents')
            and (ORDER_DETAILS.search(query) or state.get('post_purchase') or re.search(r'плат[её]жк|спам|кабинет|браузер|ссылк|чек|квитанц|скрин|приложи|скинут|отправит', query))
            and not is_closing(text) and not EXTRA_PURCHASE.search(query)):
        # бот сам попросил детали по заказу — принимаем их в обращение, а не ищем товар по случайным словам
        append_event(db, row['id'], 'customer_details', 'order')
        return 'Спасибо, добавил к обращению. Менеджер увидит это сообщение и ответит здесь.', []
    if (not action and state.get('post_purchase_reason') == 'order_question'
            and re.search(r'\bключ\s+(?:ещ[её]\s+)?не\s+активировали\b', query)):
        return 'Менеджер проверит условия по вашему заказу. ' + enter_queue(db, row, state, 'order_question'), []
    topic = support_topic(query) if text and not action and not QUOTE_REQUISITES.search(text) else None
    if topic:   # «купил КриптоПро, не активируется ключ» — вопрос по заказу, а не новая продажа
        answer, reason = topic
        already_helped = state.get('post_purchase')
        state['post_purchase'] = True
        if reason:
            state['post_purchase_reason'] = reason
        if EXTRA_PURCHASE.search(query):   # «…и ещё нужен Office на 5 мест» — вторую часть не теряем
            answer += 'Покупку из вашего сообщения посчитаю отдельно — напишите её следующим сообщением. '
        if already_helped and SUPPORT_TRIED.search(query):
            return enter_queue(db, row, state, state.get('post_purchase_reason', 'order_question')), []
        if re.search(r'спам\w*.{0,25}проверен', query):
            return answer + ' ' + enter_queue(db, row, state, state.get('post_purchase_reason', 'order_question')), []
        return answer, JOIN_MANAGER
    if (state.get('post_purchase') and text and not action and not is_closing(text)
            and not EXTRA_PURCHASE.search(query) and not QUOTE_REQUISITES.search(text)):
        if row['state'] == 'pending':
            append_event(db, row['id'], 'customer_details', 'order')
            return 'Спасибо, добавил к обращению. Менеджер увидит это сообщение и ответит здесь.', []
        reason = state.get('post_purchase_reason', 'order_question')
        return 'Менеджер проверит ваш заказ. ' + enter_queue(db, row, state, reason), []
    if action == 'invoice' or INVOICE_REQUEST.search(query):
        state['requested_invoice'] = True
        if state.get('offer_id') and state.get('quantity') and not QUOTE_REQUISITES.search(text):
            return queue_quote(db, row, state, catalog)
    if CRYPTO_NAME.search(query) and VIPNET_NAME.search(query):
        append_event(db, row['id'], 'product_comparison', 'cryptopro_vipnet')
        return CSP_COMPARISON, JOIN_MANAGER
    if re.search(r'\b(?:windows|виндовс)\b.{0,20}(?:для\s+дома|домашн)', query) and not re.search(r'\b(?:pro|server)\b', query):
        offer = lookup(catalog, '380389')
        if offer and offer['available'] and offer['price_kopecks']:
            state.update(flow=None, g_family=offer['family'], offer_id=offer['id'])
            return (f'{offer["name"]} — {chat_price(offer["price_kopecks"])} за одну лицензию. '
                    f'Карточка: {offer["url"]}.'), [('Подготовить КП', 'quote', '')]
    if re.search(r'\b(?:nano\s*cad|нано\s*кад)\b', query) and not re.search(r'спдс|geonics|геоникс|конструкц|платформ', query):
        return 'У Нанософт несколько продуктов nanoCAD. Нужна базовая платформа или отраслевой модуль, например СПДС?', []
    if re.search(r'как\s+(?:подобрать|выбрать).{0,35}\bpdf\b|подбер\w*.{0,35}для\s+работы\s+с\s+pdf', query):
        return 'Что нужно делать с PDF: редактировать, подписывать или распознавать сканы?', []
    if (state.get('flow') == 'cryptopro' or CRYPTO_NAME.search(query)) and re.search(r'дистрибутив|(?:где|как)\s+скачат', query):
        return ('Дистрибутив КриптоПро CSP 5.0 доступен у разработчика. Откройте раздел «Ссылки» на странице продукта, '
                'выберите «Скачать КриптоПро CSP 5.0» и войдите в аккаунт: https://cryptopro.ru/products/csp'), JOIN_MANAGER
    if KASPERSKY_CENTER.search(query) and (state.get('kaspersky_center') or 'kaspersky' in query or 'касперск' in query or 'kes' in query):
        state['kaspersky_center'] = True
        return ('Базовая консоль Kaspersky Security Center доступна для управления защитой организации. '
                'Для дополнительных возможностей может потребоваться коммерческая лицензия. '
                'Сравнение режимов у производителя: https://support.kaspersky.com/ksc/14/ru-RU/65277.htm'), JOIN_MANAGER
    if ANYDESK_NAME.search(query):
        state['anydesk_requested'] = True
        if re.search(r'\bдо\s+\d+\s+компьютер', digits(query)) and not re.search(r'одновременн', query):
            return 'Для AnyDesk важно число одновременных подключений. Сколько сеансов требуется одновременно?', []
    if state.get('anydesk_requested') and re.search(r'\b1\s+(?:одновременн\w*\s+)?подключени', digits(query)):
        offer = lookup(catalog, '402266')
        if offer and offer['available'] and offer['price_kopecks']:
            state.update(offer_id=offer['id'], quantity=1, awaiting_customer=True)
            return (f'{offer["name"]}: {chat_price(offer["price_kopecks"])} по каталогу за одну лицензию. '
                    f'Карточка: {offer["url"]}. {QUOTE_CUSTOMER_PROMPT}'), [('Подготовить КП', 'quote', '')]
    if re.fullmatch(r'(?:рассмотрим\s+)?(?:российск|отечественн)\w*\s+сервер\w*[.!? ]*', query):
        return 'Нужна российская серверная операционная система или серверное оборудование?', []
    if re.search(r'\b(?:касперск\w*|kaspersky)\b', query) and re.search(r'\bstandard\b', query) and not re.search(r'бизнес|endpoint|организац', query):
        state['kaspersky_standard'] = True
        if not state.get('quantity'):
            return 'Kaspersky Standard нужен как новая лицензия или продление и на сколько устройств?', []
    if state.get('kaspersky_standard') and state.get('quantity') == 5 and re.search(r'на\s+(?:1\s+)?год', query):
        offer = lookup(catalog, '416859')
        if offer and offer['available'] and offer['price_kopecks']:
            state.update(offer_id=offer['id'], g_family=offer['family'], awaiting_customer=True)
            return (f'{offer["name"]} — {chat_price(offer["price_kopecks"])} за пакет на 5 устройств. '
                    f'Карточка: {offer["url"]}. {QUOTE_CUSTOMER_PROMPT}'), [('Подготовить КП', 'quote', '')]
    if re.search(r'кас[пп]ерск|kaspersky', query) and re.search(r'фст[эе]к', query):
        state['kaspersky_certified'] = True
    if state.get('kaspersky_certified') and (re.search(r'фст[эе]к', query) or state.get('quantity') == 1):
        return ('Для сертифицированной ФСТЭК поставки нужна отдельная позиция. '
                'Подтверждённую цену на один компьютер по каталогу не нашёл. На какой срок нужна лицензия?'), JOIN_MANAGER
    if 'дистрибутив' in query and ('криптоарм' in query or 'криптоарм' in normalize(state.get('g_text', ''))):
        return ('Установочный дистрибутив КриптоАРМ 5 можно скачать у разработчика: https://cryptoarm.ru/cryptoarm-5/. '
                'Лицензия активирует выбранную редакцию. Подтверждение состава конкретной поставки доступно в карточке товара.'), JOIN_MANAGER
    if state.get('flow') == 'cryptopro' and re.search(r'обновлен\w*', query) and re.search(r'верси|платн', query):
        return ('Оплата обновления зависит от версии и условий вашей лицензии. Стоимость перехода на названную версию '
                'уточнит менеджер. У производителя есть отдельные лицензии на обновление: https://cryptopro.ru/faq/how-to-buy'), JOIN_MANAGER
    if 'redcheck' in query and re.search(r'чем отлич|отличи|в чем разниц', query) and 'сетев' in query:
        state['redcheck_follow_up'] = True
        return ('Производитель указывает для RedCheck Professional лицензирование по числу IP-адресов (DNS-имён). '
                'Отдельные условия позиции с пометкой «сетевая версия» в сравнении редакций не раскрыты, их подтвердит менеджер. '
                'Условия производителя: https://www.redcheck.ru/licensing/'), JOIN_MANAGER
    if (state.get('inn_rejected') and state.get('inn_rejected_turn') != state['turn_no'] and INN_CONFIRM.search(query)
            and not INN_FORMAT.search(text)):
        # «Да, ИНН верный, формируйте» после вопроса о контрольной цифре — принимаем тот же ИНН, менеджер проверит
        accept_inn(state, state['inn_rejected'])
        if state.get('offer_id'):
            return queue_quote(db, row, state, catalog)
    if text and not state.get('awaiting_customer') and QUOTE_REQUISITES.search(text) and state.get('flow') != 'mdaemon':
        remember_quote_customer(state, text)
        if state.get('flow') == 'cryptopro' and state.get('offer_id') and state.get('quantity'):
            return queue_quote(db, row, state, catalog)
        needs_items = state.get('needs_quote_items')
        if state.get('flow') == 'needs' and needs_items and all(item['quantity'] == state.get('quantity') for item in needs_items):
            state['g_items'] = needs_items
            return queue_quote(db, row, state, catalog)
    if state.get('awaiting_customer') and text and (QUOTE_REQUISITES.search(text) or re.search(r'\b(?:ооо|ао|пао|зао|ип|гбу|мбу|фгуп)\b|[«"]', query)
                                                    or INN_FORMAT.search(text)):
        remember_quote_customer(state, text)
        if tool == 'draft_quote' and state.get('customer') and state.get('inn') and (state.get('kpp') or len(state['inn']) == 12):
            append_event(db, row['id'], 'model_tool_executed', tool)
        return queue_quote(db, row, state, catalog)
    if state.get('flow') == 'mdaemon' and QUOTE_REQUISITES.search(text):
        offers = state.get('offered_ids', [])
        if len(offers) == 1:
            state['offer_id'] = offers[0]
            remember_quote_customer(state, text)
            return queue_quote(db, row, state, catalog)
    if re.search(r'оператор', query):
        return enter_queue(db, row, state, 'customer_request'), []
    if re.search(r'закрывающ|\bупд\b', query):
        hint = ('По заказам юрлиц документы (счёт, УПД или акт) высылают по почтовому адресу из заказа; через ЭДО — заявка менеджеру или на '
                'edo@softline.com (https://store.softline.ru/delivery_info/#q7). ')
        if re.search(r'оплачен|переслать|переда|пришлите|отправьте|нужен|нужны', query):
            return hint + enter_queue(db, row, state, 'closing_documents'), []
        return hint + 'Если документов нет, могу позвать оператора.', JOIN_MANAGER
    if re.search(r'(?:где|получить|пришел|найти).{0,25}ключ\w*\s*(?:лицензи|заказа|$)', query) and not re.search(r'\bне\s+(?:приш|приход)', query):
        return 'Ключ приходит письмом на почту из заказа; статус и данные доставки — в личном кабинете Softline по ссылке из письма о заказе (https://store.softline.ru/delivery_info/#q2).', JOIN_MANAGER
    match = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(?:%|процент)', query)
    discount = Decimal(match.group(1).replace(',', '.')) if match else None
    if action == 'more_discount' or re.search(r'(?:больш|выше).{0,35}(?:скид|купон|%)|(?:скид|купон).{0,30}(?:больш|выше)', query) or (discount is not None and discount > 5):
        return enter_queue(db, row, state, 'discount_over_limit'), []
    if action != 'deferral' and re.search(r'скидк|купон', query) and not re.search(r'отсроч|постоплат', query) and state.get('g_items'):
        # скидка после расчёта нескольких позиций — к общему итогу, без нового поиска товара
        percent = int(discount) if discount is not None else 5
        state['coupon_percent'] = str(percent)
        append_event(db, row['id'], 'demo_coupon_offered', str(percent))
        with closing(read_only(catalog)) as cat:
            total = 0
            for item in state['g_items']:
                found = cat.execute('SELECT price_kopecks FROM products WHERE id=?', (item['id'],)).fetchone()
                total += (found['price_kopecks'] or 0) * (item.get('units') or item['quantity'] or 1) if found else 0
        return (f'Итого по {len(state["g_items"])} позициям: {chat_price(total)}, со скидкой {percent}% — {chat_price(discounted(total, percent))}. '
                'Скидку до 5% даю сам по купону, больше — только через менеджера. Для КП пришлите название организации, ИНН и КПП.'), [
                    ('Подготовить КП', 'quote', ''), ('Запросить больше', 'more_discount', '')]
    if action != 'deferral' and re.search(r'скидк|купон', query) and not re.search(r'отсроч|постоплат', query):
        general = catalog_turn(catalog, state, text, queue=lambda reason: enter_queue(db, row, state, reason),
                               quote=lambda: queue_quote(db, row, state, catalog))
        product = lookup(catalog, state['offer_id']) if state.get('offer_id') else None
        if product and product['price_kopecks']:
            qty = purchasable_units(product, state['quantity']) if state.get('quantity') else 1
            qty = qty or state.get('quantity') or 1
            total = product['price_kopecks'] * qty
            percent = int(discount) if discount is not None else 5
            state['coupon_percent'] = str(percent)
            append_event(db, row['id'], 'demo_coupon_offered', str(percent))
            head = (general[0] + '\n') if general and general[0] and 'Нашёл' in general[0] else ''
            if not head:  # называем позицию и карточку: клиент и проверка видят, от какой цены скидка
                head = f'{product["name"]}' + (f' ({product["url"]})' if product.get('url') else '') + (f', {qty} шт.' if qty > 1 else '') + '.\n'
            return (head + f'Со скидкой {percent}%: {chat_price(discounted(total, percent))} вместо {chat_price(total)}. '
                    'Скидку до 5% даю сам по купону, больше — только через менеджера.'), [('Подготовить КП', 'quote', ''), ('Запросить больше', 'more_discount', '')]
        if general and state.get('g_family'):
            return general[0] + '\nСкидку до 5% даю сам по купону, больше — через менеджера.', general[1]
    if action == 'deferral' or re.search(r'отсроч|постоплат|скидк|купон', query):
        percent = discount if discount is not None else 5
        state['coupon_percent'] = str(percent)
        append_event(db, row['id'], 'demo_coupon_offered', str(percent))
        return f'Оплата по оферте — предоплата. Предлагаю демонстрационный купон на {percent}%. За большей скидкой подключу менеджера.', [('Запросить больше', 'more_discount', ''), *JOIN_MANAGER]
    annual = bool(re.search(r'\bна\s+год|годов', query)) and (
        not re.search(r'бессроч', query) or bool(re.search(r'бессрочн\w*\s+(?:отпада|не\s+нужн|не\s+подход|не\s+надо)|передумал', query)))
    if annual and state.get('flow') == 'cryptopro':
        # клиент передумал: годовая вместо бессрочной — дальше общий разговор по каталогу
        state['flow'] = None
        for key in ('offer_id', 'offered_ids', 'awaiting_customer'):
            state.pop(key, None)
    if CRYPTO_NAME.search(query) and not CRYPTO_OTHER.search(query) and not re.search(r'физ\w*\s*лиц', query) and not annual:
        state.update(flow='cryptopro', query=text)
        state.pop('offer_id', None)
        state.pop('offered_ids', None)
    if MDAEMON_NAME.search(query):
        state.update(flow='mdaemon', query=text)
        if MDAEMON_STANDARD.search(query):
            state['standard_requested'] = True
    if re.search(r'\b(?:pam\s+indeed|indeed\s+pam)\b', query):
        return 'Не нашёл Indeed PAM в каталоге. ' + enter_queue(db, row, state, 'not_in_catalog'), []
    if SMOLENSK.search(query):
        state['flow'] = 'smolensk'
        return '«Смоленск» нужен для рабочей станции или для сервера?', []
    if state.get('flow') == 'smolensk' and re.search(r'рабоч\w+|сервер', query):
        if catalog.is_file() and re.search(r'рабоч\w*\s+станц', query) and 'бессроч' in query:
            with closing(read_only(catalog)) as cat:
                offer = cat.execute('''SELECT id, price_kopecks, url FROM products
                    WHERE name LIKE 'ALSE%Смоленск%рабочей станции%' AND available=1 AND price_kopecks>0
                      AND json_extract(parameters, '$.Срок действия')='бессрочная'
                      AND json_extract(parameters, '$.Тип организации')='Академическая'
                    ORDER BY price_kopecks, id LIMIT 1''').fetchone()
            if offer:
                state['smolensk_academic'] = offer['id']
                return (f'В каталоге есть бессрочная академическая лицензия Astra Linux «Смоленск» для рабочей станции '
                        f'от {chat_price(offer["price_kopecks"])} за лицензию. Карточка: {offer["url"]}. '
                        'Вы закупаете для учебного заведения или коммерческой организации?'), JOIN_MANAGER
        return 'Точный артикул и цену для этой комплектации нужно сверить. ' + enter_queue(db, row, state, 'price_confirmation'), []
    if NEEDS_QUERY.search(query) and not state.get('g_family'):
        append_event(db, row['id'], 'requirements_understood', 'software_protection')
        state.update(flow='needs', query=text)
        if tool == 'clarify_requirements':
            field = next_clarify_field(state)
            append_event(db, row['id'], 'model_tool_executed', f'{tool}:{field}' if field else tool)
            return collect_selection(state, catalog, db, row['id'])
    workstation_hint = bool(re.search(
        r'\d+\s*мест|рабоч\w*\s+мест|рабоч\w*\s+станц|\bкомпьютер\w*|\bпк\b|ноутбук\w*|windows|виндовс|на\s+одн[оау]\w*\s+(?:машин|пк|комп|устройств)',
        query,
    ))
    if state.get('flow') == 'cryptopro' and not state.get('offer_id') and action != 'placement' and not re.search(r'сервер', query) and (
            workstation_hint or (re.search(r'\bcsp\b|\bксп\b|5\.0', query) and re.search(r'бессроч', query))):
        action, value = 'placement', 'workstation'
    if action == 'placement' or (state.get('flow') == 'cryptopro' and (workstation_hint or re.search(r'\bсервер\w*', query))):
        placement = value if action == 'placement' else 'server' if 'сервер' in query else 'workstation'
        if placement == 'server':
            return 'Для сервера нужна другая позиция. ' + enter_queue(db, row, state, 'server_license'), []
        if placement != 'workstation':
            return 'Уточните тип лицензии.', WORKPLACE_CHOICES
        product = lookup(catalog, CRYPTO_WORKSTATION)
        if not product or not product['available'] or not product['price_kopecks']:
            return enter_queue(db, row, state, 'catalog_unavailable'), []
        state['offer_id'] = product['id']
        line = f'{product["name"]} — {chat_price(product["price_kopecks"])}. {product["url"]}'
        if CUSTOM_UNIT_PRICE.search(query):
            line = 'В КП использую цену из каталога. Индивидуальную цену согласует менеджер.\n' + line
        if state.get('quantity'):
            state['awaiting_customer'] = True
            if re.search(r'\bинн\b', query):  # заказ и реквизиты в одной реплике — сразу КП
                remember_quote_customer(state, text)
                return queue_quote(db, row, state, catalog)  # недостающее или ошибочное поле назовёт сама проверка
            amount = product['price_kopecks'] * state['quantity']
            return f'{line}\nНа {state["quantity"]} шт. — {chat_price(amount)}. {QUOTE_CUSTOMER_PROMPT}', [('Подготовить КП', 'quote', '')]
        return f'{line}\nСколько рабочих мест?', [('Подготовить КП', 'quote', '')]
    if action == 'select_offer' and value in state.get('offered_ids', []):
        if tool == 'draft_quote':
            append_event(db, row['id'], 'model_tool_executed', tool)
        state['offer_id'] = value
        if state.pop('needs_quote_items', None) is not None:
            state.pop('g_items', None)
        return queue_quote(db, row, state, catalog)
    if action == 'quote' or (state.get('offer_id') and ('кп' in query or 'коммерческ' in query)):
        return queue_quote(db, row, state, catalog)
    if state.get('flow') == 'cryptopro':
        if state.get('offer_id') and state.get('quantity'):
            state['awaiting_customer'] = True
            return QUOTE_CUSTOMER_PROMPT, []
        if not state.get('crypto_placement_asked'):
            state['crypto_placement_asked'] = True
            return 'Лицензии КриптоПро нужны на рабочие места или на сервер?', WORKPLACE_CHOICES
        state['flow'] = None
    if state.get('flow') in ('needs', 'mdaemon'):
        if action == 'term' and value in {'12', '24'}:
            state['term'] = int(value)
            state.pop('term_assumed', None)
        elif text:
            terms = [months for months, pattern in TEXT_TERMS if pattern.search(query)]
            if len(terms) == 1:
                state['term'] = terms[0]
                state.pop('term_assumed', None)
        if action == 'deployment' and value in {'local', 'cloud', 'flexible'}:
            state['deployment'] = value
        elif text:
            local = bool(LOCAL_DEPLOYMENT.search(query))
            cloud = bool(CLOUD_DEPLOYMENT.search(query)) and not re.search(r'\bне\s+в\s+облак|\bбез\s+облак', query)
            if local != cloud:
                state['deployment'] = 'local' if local else 'cloud'
        if action == 'focus' and value in {'mail', 'all'}:
            state['focus'] = value
        elif state['flow'] == 'needs' and not state.get('focus') and not NEEDS_QUERY.search(query):
            if re.search(r'\b(?:вместе|и почта,?\s+и файлы|почт\w+.{0,70}компьютер|компьютер\w*.{0,40}почт)', query):
                state['focus'] = 'all'
            elif re.search(r'\b(?:только|сначала)\s+почт', query):
                state['focus'] = 'mail'
        registry = bool(REGISTRY_QUERY.search(query))
        ready = bool(state.get('quantity') and state.get('term') and state.get('deployment') and
                     (state['flow'] != 'needs' or state.get('focus')))
        if ready:
            if tool == 'check_registry' and registry:
                append_event(db, row['id'], 'model_tool_executed', tool)
                return collect_selection(state, catalog, db, row['id'], registry=True)
            if tool == 'search_catalog' and not registry:
                append_event(db, row['id'], 'model_tool_executed', tool)
                return collect_selection(state, catalog, db, row['id'])
        return collect_selection(state, catalog, db, row['id'], registry)
    general = catalog_turn(catalog, state, text, queue=lambda reason: enter_queue(db, row, state, reason),
                           quote=lambda: queue_quote(db, row, state, catalog), page_url=page_url)
    if general is not None:
        return general
    candidates = resolve_product(catalog, text, state.get('quantity'), page_url)
    if candidates:
        if len(candidates) == 1 and (not candidates[0]['available'] or candidates[0]['price_kopecks'] is None):
            return enter_queue(db, row, state, 'price_confirmation'), []
        state['flow'] = 'catalog_reference'
        state['offered_ids'] = [item['id'] for item in candidates]
        lines = ['Нашёл в каталоге:']
        for item in candidates:
            price = chat_price(item['price_kopecks']) if item['price_kopecks'] is not None else 'по запросу'
            lines.append(f'{item["name"]} — {price} {item["url"] or ""}')
        return '\n'.join(lines), [('Выбрать: ' + item['name'][:45], 'select_offer', item['id']) for item in candidates]
    if intent_hint == 'handoff':
        return enter_queue(db, row, state, 'model_routing'), []
    if intent_hint == 'help':
        return 'Что нужно проверить по заказу: статус, документы или лицензионный ключ?', JOIN_MANAGER
    if intent_hint == 'selection':
        return 'Какую задачу должно решить ПО? Например, защитить почту и файлы. Укажите примерное число сотрудников.', JOIN_MANAGER
    if PURCHASE_WORDS.search(query) or action in ('price', 'invoice') or intent_hint in {'price', 'quote', 'invoice'}:
        state['flow'] = 'awaiting_product'
        return 'Какой продукт нужен? Напишите название, артикул или ссылку на карточку — проверю цену по каталогу.', JOIN_MANAGER
    return 'Подскажите, какой продукт или какую задачу нужно решить? Подберу по каталогу или позову оператора.', JOIN_MANAGER
