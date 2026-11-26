import re
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from .catalog import find_matches, normalize, purchasable_units, read_only, view
from .documents import rubles
from .selection import Selection, selection_result
from .store import append_event


CRYPTO_WORKSTATION = '410137'
CRYPTO_NAME = re.compile(r'крипто\s*про|crypto\s*pro')
NEEDS_QUERY = re.compile(r'защит.*(?:почт|файл)|(?:почт|файл).*защит')
REGISTRY_QUERY = re.compile(r'российск|отечествен|реестр')
REGISTRY_REFERENCES = (
    ('kaspersky security для почтовых серверов базовая лицензия', '203'),
    ('kaspersky endpoint security для бизнеса стандартный базовая лицензия', '205'),
    ('kaspersky total security для бизнеса базовая лицензия', '204'),
)
REGISTRY_SOURCE = 'https://reestr.digital.gov.ru/reestr/?EX_PAGE_N=12&EX_PAGE_S=100&PAGE_N=304&PAGE_S=100'
WORKPLACE_CHOICES = [('Рабочие места', 'placement', 'workstation'), ('Сервер', 'placement', 'server')]
JOIN_MANAGER = [('Позвать оператора', 'handoff', '')]
QUOTE_CUSTOMER_PROMPT = (
    'Для КП укажите название организации, ИНН и КПП. '
    'Для проверки стенда используйте тестовые реквизиты: ООО «Демо», ИНН 0000000000, КПП 000000000.'
)
QUOTE_REQUISITES = re.compile(r'\b(ИНН|КПП)\b[\s:=№]*([0-9][A-Za-z0-9]*)', re.I)
INN_FORMAT = re.compile(r'(?:[0-9]{10}|[0-9]{12})')
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
    if CRYPTO_NAME.search(query) or re.search(r'mdaemon|защит.*(?:почт|файл)|закрывающ|отсроч|оператор|купон|скидк', query):
        return ''
    tokens = [w for w in PRODUCT_WORDS.findall(query) if w in INTENT_CUES]
    return ' '.join(tokens[:20]) if len(tokens) >= 2 else ''


def tool_request(text: str, action: str | None, value: str, state: dict):
    """Return only scenario facts suitable for the model, never the customer's raw input."""
    query = normalize(text)
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
    if action == 'handoff' or re.search(r'позовите оператора|свяжите с менеджером|запросить цену|тендер', query):
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
    db.execute("UPDATE cases SET state='pending',version=version+1,payment_due=NULL WHERE id=?", (row['id'],))
    append_event(db, row['id'], 'sent_to_manager', reason)
    return 'Передал запрос менеджеру. Его ответ появится в этом чате.'


def remember_quote_customer(state, text: str):
    for field, value in QUOTE_REQUISITES.findall(text):
        if field.upper() == 'ИНН' and INN_FORMAT.fullmatch(value):
            state['inn'] = value
        if field.upper() == 'КПП' and KPP_FORMAT.fullmatch(value):
            state['kpp'] = value.upper()
    name = QUOTE_REQUISITES.sub(' ', text).strip(' \t\r\n,:;.-')
    if name == text.strip(' \t\r\n,:;.-'):
        if KPP_FORMAT.fullmatch(name):
            state['kpp'] = name.upper()
            return
        bare_inn = re.search(r'(?<!\w)([0-9]{10}|[0-9]{12})(?!\w)', name)
        if bare_inn:
            state['inn'] = bare_inn[1]
            name = (name[:bare_inn.start()] + name[bare_inn.end():]).strip(' \t\r\n,:;.-')
    name = re.sub(r'^(?:название(?: организации)?|организация|компания)\s*:\s*', '', name, flags=re.I)
    if any(char.isalpha() for char in name) and not re.search(r'\b(?:инн|кпп)\b', name, re.I):
        state['customer'] = ' '.join(name.split())[:100]


def queue_quote(db, row, state, catalog: Path):
    if not state.get('offer_id'):
        return 'Сначала выберите позицию каталога, для которой нужно КП.', []
    if not state.get('quantity'):
        return 'На сколько лицензий подготовить КП?', []
    missing = [label for key, label in (('customer', 'название организации'), ('inn', 'ИНН'), ('kpp', 'КПП')) if not state.get(key)]
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
    if quantity is None:
        return 'Количество и цену для выбранной лицензии нужно сверить. ' + enter_queue(db, row, state, 'price_confirmation'), []
    state['quote'] = {
        'offer': product, 'quantity': quantity, 'customer': state['customer'], 'inn': state['inn'], 'kpp': state['kpp'],
        'requested_users': requested_users,
        'amount_kopecks': product['price_kopecks'] * quantity, 'vat_kopecks': None,
        'vat_status': 'НДС уточняется менеджером', 'payment_terms': 'Предоплата по оферте',
        'source_date': product['source_date'],
    }
    state['awaiting_customer'] = False
    append_event(db, row['id'], 'quote_amount_calculated', str(state['quote']['amount_kopecks']))
    message = enter_queue(db, row, state, 'quote_review')
    return f'Сумма по каталогу: {chat_price(state["quote"]["amount_kopecks"])}. {message}', []


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


def collect_selection(state, catalog: Path, db, case_id: str, registry=False):
    if not catalog.is_file():
        return 'Каталог ещё недоступен. Могу позвать оператора.', JOIN_MANAGER
    if state['flow'] == 'needs':
        if not state.get('focus'):
            return 'Выбираем защиту для почты и файлов вместе или начинаем с почты?', [('И почта, и файлы', 'focus', 'all'), ('Сначала почта', 'focus', 'mail')]
    if not state.get('term'):
        return 'На какой срок нужна лицензия?', [('12 месяцев', 'term', '12'), ('24 месяца', 'term', '24')]
    if not state.get('deployment'):
        return 'Где будет работать решение?', [('Свои серверы', 'deployment', 'local'), ('Облако', 'deployment', 'cloud'), ('Оба варианта', 'deployment', 'flexible')]
    if not state.get('quantity'):
        return 'Сколько пользователей или устройств нужно покрыть?', []
    query = 'защита почты' if state.get('focus') == 'mail' else state['query']
    req = Selection(mode='known' if state['flow'] == 'mdaemon' else 'needs',
                    query=query, product='MDaemon Standard' if state['flow'] == 'mdaemon' else '',
                    users=state['quantity'], term_months=state['term'], deployment=state['deployment'], require_registry=registry)
    append_event(db, case_id, 'registry_lookup' if registry else 'catalog_search', req.mode)
    with closing(read_only(catalog)) as catalog_db:
        result = selection_result(catalog_db, req)
        if registry:
            enriched = {g['topic']: g for g in result['groups']}
            for group in registry_selection(catalog_db, req):
                enriched.setdefault(group['topic'], group)
            result['groups'] = list(enriched.values())
    shown = [(group['topic'], offer) for group in result['groups'] for offer in group['offers'][:1]]
    if not shown:
        return ('По фиду не нашёл подходящий вариант с подтверждённой записью в реестре.' if registry else 'По этим требованиям точного варианта в выдаче нет.') + ' Могу позвать оператора.', JOIN_MANAGER
    state['offered_ids'] = [offer['id'] for _, offer in shown]
    lines = ['Варианты по данным каталога:']
    if state['flow'] == 'mdaemon':
        lines.append('Точное название Standard в фиде не подтверждено. Ниже — MDaemon Messaging Server для проверки.')
    if registry:
        lines.append('Номера из реестра отечественного ПО. Источник указан рядом, если он известен.')
    for topic, offer in shown:
        price = chat_price(offer['price_kopecks']) if offer['price_kopecks'] is not None else 'цену уточнит менеджер'
        registry_text = f', реестр № {offer["registry"]} {offer.get("registry_source", "")}' if registry else ''
        units = purchasable_units(offer, state['quantity'])
        total = f' × {units} = {chat_price(offer["price_kopecks"] * units)}' if units and units > 1 and offer['price_kopecks'] else ''
        lines.append(f'{topic}: {offer["name"]} — {price}{total}{registry_text}. Карточка: {offer["url"] or ""}')
    return '\n'.join(lines), [(f'Выбрать: {topic}', 'select_offer', offer['id']) for topic, offer in shown]


def run_turn(db, row, state, catalog: Path, *, text='', action=None, value='', intent_hint='unknown', page_url='', tool=None):
    query = normalize(text)
    count = re.search(r'\b([1-9]\d{0,3})\s*(?:бессрочн\w*\s+)?(?:лицензи|сотрудник|пользовател|рабочих\s+мест|узл|ящик|мест)', query)
    if count:
        state['quantity'] = int(count.group(1))
    if tool == 'contact_manager':
        append_event(db, row['id'], 'model_tool_executed', tool)
        return enter_queue(db, row, state, 'model_routing'), []
    if action == 'handoff' or re.search(r'(?:позови|подключи|соедини)\w*\s+(?:с\s+)?(?:оператор|менеджер)', query):
        return enter_queue(db, row, state, 'customer_request'), []
    if state.get('awaiting_customer') and text:
        remember_quote_customer(state, text)
        if tool == 'draft_quote' and all(state.get(field) for field in ('customer', 'inn', 'kpp')):
            append_event(db, row['id'], 'model_tool_executed', tool)
        return queue_quote(db, row, state, catalog)
    if re.search(r'оператор|тендер|госзакупк|запросить цену', query):
        return enter_queue(db, row, state, 'customer_request'), []
    if re.search(r'закрывающ|\bупд\b', query):
        return 'Закрывающие документы по заказу проверьте в личном кабинете Store: https://store.softline.ru/ — войдите и откройте заказ. Если документов там нет, могу позвать оператора. Справка: https://docs.softline.com/ru-ru', JOIN_MANAGER
    if re.search(r'статус\s+заказа|(?:где|получить|пришел|найти).{0,25}ключ\w*\s*(?:лицензи|заказа|$)', query):
        return 'Статус и данные электронной доставки проверяются в вашем заказе в личном кабинете Store: https://store.softline.ru/. Справка: https://docs.softline.com/ru-ru', JOIN_MANAGER
    match = re.search(r'\b(\d+(?:[.,]\d+)?)\s*%', query)
    discount = Decimal(match.group(1).replace(',', '.')) if match else None
    if action == 'more_discount' or re.search(r'(?:больш|выше).{0,35}(?:скид|купон|%)|(?:скид|купон).{0,30}(?:больш|выше)', query) or (discount is not None and discount > 5):
        return enter_queue(db, row, state, 'discount_over_limit'), []
    if action == 'deferral' or re.search(r'отсроч|постоплат|скидк|купон', query):
        percent = discount if discount is not None else 5
        state['coupon_percent'] = str(percent)
        append_event(db, row['id'], 'demo_coupon_offered', str(percent))
        return f'Оплата по оферте — предоплата. Предлагаю демонстрационный купон на {percent}%. За большей скидкой подключу менеджера.', [('Запросить больше', 'more_discount', ''), *JOIN_MANAGER]
    if CRYPTO_NAME.search(query):
        state.update(flow='cryptopro', query=text)
        state.pop('offer_id', None)
        state.pop('offered_ids', None)
    if 'mdaemon' in query:
        state.update(flow='mdaemon', query=text)
    if NEEDS_QUERY.search(query):
        append_event(db, row['id'], 'requirements_understood', 'software_protection')
        state.update(flow='needs', query=text)
        if tool == 'clarify_requirements':
            append_event(db, row['id'], 'model_tool_executed', tool)
            return collect_selection(state, catalog, db, row['id'])
    if action == 'placement' or (state.get('flow') == 'cryptopro' and re.search(r'рабоч\w*\s+мест|\bсервер\w*', query)):
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
        if state.get('quantity'):
            state['awaiting_customer'] = True
            amount = product['price_kopecks'] * state['quantity']
            return f'{line}\nНа {state["quantity"]} шт. — {chat_price(amount)}. {QUOTE_CUSTOMER_PROMPT}', [('Подготовить КП', 'quote', '')]
        return f'{line}\nСколько рабочих мест?', [('Подготовить КП', 'quote', '')]
    if action == 'select_offer' and value in state.get('offered_ids', []):
        if tool == 'draft_quote':
            append_event(db, row['id'], 'model_tool_executed', tool)
        state['offer_id'] = value
        return queue_quote(db, row, state, catalog)
    if action == 'quote' or (state.get('offer_id') and ('кп' in query or 'коммерческ' in query)):
        return queue_quote(db, row, state, catalog)
    if state.get('flow') == 'cryptopro':
        if state.get('offer_id') and state.get('quantity'):
            state['awaiting_customer'] = True
            return QUOTE_CUSTOMER_PROMPT, []
        return 'Лицензии КриптоПро нужны на рабочие места или на сервер?', WORKPLACE_CHOICES
    if state.get('flow') in ('needs', 'mdaemon'):
        if action == 'term' and value in {'12', '24'}:
            state['term'] = int(value)
        if action == 'deployment' and value in {'local', 'cloud', 'flexible'}:
            state['deployment'] = value
        if action == 'focus' and value in {'mail', 'all'}:
            state['focus'] = value
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
        return 'Пришлите название, артикул или ссылку на карточку товара. Проверю цены и варианты по каталогу.', JOIN_MANAGER
    return 'Помогу подобрать ПО или позову оператора. Напишите название продукта или расскажите, какую задачу нужно решить.', JOIN_MANAGER
