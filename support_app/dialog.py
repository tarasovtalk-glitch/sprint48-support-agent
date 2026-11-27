"""Общий разговор о любом товаре каталога: понять товар и условия, назвать цену из каталога, собрать КП.

Работает после прописанных сценариев chat.run_turn и вместо прежних заготовок
«Пришлите название…» и «Помогу подобрать…». Цены и суммы берутся только из каталога, модель их не пишет.
Состояние разговора хранится в chat_state (ключи g_*), поэтому агент помнит товар, количество и срок между репликами.
"""
import difflib
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .catalog import KASPERSKY_FAMILIES, discounted, kaspersky_tier, normalize, read_only, tiered_annual_offer, view

# ── слова, которые не называют товар ──────────────────────────────────────────
STOP = set('''
одно один одна одного одной одну одним примерно приблизительно хоть цифр порядок порядка
а без бы был была были быть в вам вас ваш ваша ваше вашу вот все всё вы где да для до его ее её если есть еще ещё же за и из или им их
к как какая какие какой когда кто ли либо мне мной могу можно мой мы на над нам нас наш не нет ни но ну о об от по под при про с со
так там то тоже только у уже чем что чтобы эта это этот я ли бы же ведь вообще именно просто очень там тут
добрый день добрый вечер утро здравствуйте здравствуй привет приветствую доброго времени суток уважаемые коллеги товарищи
пожалуйста подскажите подскажете скажите подскажи помогите поможете интересует интересуют хотим хотел хотела хотели хочу нужна нужно
нужен нужны необходимо необходима требуется требуются купить купим приобрести приобрету приобретаю покупка покупку заказать оформить
стоимость стоит стоить стоят цена цену цены сколько будет почем почём прайс кп коммерческое предложение счет счёт выставить
лицензия лицензии лицензию лицензий лиц программа программу программы продукт продукта по софт
организации организацию организация фирму фирма лица лицу лиц учреждения учреждение учреждений компании компания юр юрлица юрлицо юридического лица физ физлица физического лицо
у вас вами возможно возможность ли есть имеется какая какие варианты вариант
шт штук штуки мест места рабочих рабочие рабочее место пк компьютеров компьютера компьютер человек пользователей пользователя
год года лет месяц месяца месяцев бессрочно бессрочная бессрочную навсегда новая новую продление продлить
ооо ип инн кпп тел телефон email почта почту ответа for the and of with license licence номер лицензии
ищем ищу ищете можете можем предложить предложите посоветуете посоветуйте посоветовать выбрать выбор меня мой моя моё мое свой свою своей
развернуть работает работать данное данный данная этому этой этого другой другие другую буду будем будут покупать покупаю информация информацию
аналог аналоги аналога аналогов аналогичный коммерческая коммерческий коммерческой коммерческих коммерческое оплата оплату оплатой оплате оплачу оплатим счету счёту безнал безналичный почтой регион региона регионы регион город города область доставка доставкой доставить товар товару товара товаров приобретаете приобретаем приобретать продаете продаёте продаете продаются вопрос вопросы здрасти такой такая такие также подойдет подойдёт подходит лучше хорошо нормально сейчас сегодня потом далее
'''.split())

# Разговорные и ошибочные написания → как в каталоге
ALIASES = (
    (r'касперск\w*|kasperski\w*', 'kaspersky'),
    (r'\bkes\b', 'kaspersky endpoint security'),
    (r'крипто\s*арм|cryptoarm', 'криптоарм'),
    (r'крипто\s*-?\s*про|kripto\s*pro|crypto\s*pro', 'криптопро'),
    (r'\bксп\b|\bcsp\b', 'csp'),
    (r'ани\s*деск|эни\s*деск|anydesk', 'anydesk'),
    (r'мова\w*|movavi\w*', 'мовавика'),
    (r'майкрософт|микрософт', 'microsoft'),
    (r'виндовс|виндоус', 'windows'),
    (r'\bр7[\s\-]*офис\w*|\br7[\s\-]*office\w*', 'r7office'),
    (r'архи\s*кад\w*', 'archicad'),
    (r'мсофис\w*|ms\s*office|(?:microsoft|ms)\s+о+ф+и+с\w*|\bворд\w*|\bворлд\b|эксел\w*', 'microsoft office'),
    (r'\bо+ф+и+с\b|\bоффис\w*', 'office'),
    (r'\bред\s*ос\b|\bred\s*os\b', 'ред ос'),
    (r'termidesk', 'термидеск'),
    (r'мульти\s*фактор', 'multifactor'),
    (r'рутокен|rutoken', 'рутокен'),
    (r'\bлайт\b', 'lite'),
    (r'гранд\s*-?\s*смет\w*', 'гранд смета'),
    (r'юзер\s*гейт', 'usergate'),
    (r'нано\s*кад', 'nanocad'),
    (r'др\.?\s*веб|drweb|dr\s*web', 'dr web'),
    (r'\b(?:astra|астр\w*)\s*(?:linux|линукс)?\s*(?:se|сэ|special\s+edition|спешиал)\b', 'alse'),
    (r'\bастр\w*', 'astra'),
    (r'линукс', 'linux'),
    (r'\bcorp\b', 'corporate'),
    (r'\bstandart\b|\bstandard\b', 'standard стандарт'),
    (r'\bbusiness\b', 'business бизнес'),
    (r'\beducation\b|\bedu\b', 'академ образоват'),
    (r'\bсервер\w*\b', 'server'),
    (r'\bсекрет\s*нет\b', 'secret net'),
    (r'\bсевер\s*карт\b', 'severcart'),
    (r'\bред\s*чек\b', 'redcheck'),
    (r'\bру\s*десктоп\b', 'rudesktop'),
    (r'\bвмикс\b', 'vmix'),
    (r'\bяндекс\s*360\b', 'яндекс 360'),
    (r'\bфотошоп\w*', 'photoshop'),
)
# Слово каталога «Smolensk»/«Орёл» и т. п. пишется кириллицей; оставляем как есть.

# Если товара нет, что предложить вместо (только поиск по каталогу, без выдумки)
ANALOG_SEARCH = (
    (r'power\s*bi', 'visiology'),
    (r'photoshop|adobe', 'corel'),
    (r'office\s*365|microsoft\s*365|о365', 'мойофис'),
    (r'windows\s*server', 'astra linux special edition'),
    (r'ntfs|paragon', 'ntfs'),
    (r'vmix', 'мовавика видео'),
    (r'zwcad|autocad|2d\s*cad|\bcad\b', 'nanocad'),
    (r'kaspersky|антивирус', 'dr web'),
    (r'anydesk|teamviewer|тимвьюер', 'rudesktop'),
    (r'gitlab|github|bitbucket', 'gitflic'),
)

QTY = re.compile(r'(?<![\d.,])([1-9]\d{0,4})\s*(?:-?\s*(?:х|ти|и|ми))?\s*(?:бессрочн\w*\s+)?(?:лицензи\w*|сотрудник\w*|пользовател\w*|человек\w*|чел\b|'
                 r'рабоч\w*\s+мест\w*|рабоч\w*\s+станци\w*|раб\.?\s*мест\w*|мест\w*|машин\w*|компьютер\w*|пк\b|армов|арм\b|устройств\w*|узл\w*|ящик\w*|'
                 r'штук\w*|шт\b|ip\b|ip-адрес\w*|объект\w*|ключ\w*|подключени\w*|копи\w*)')
QTY_BARE = re.compile(r'(?:^|\s)(?:на|для|нужно|нужна|нужен|необходимо)\s+([1-9]\d{0,4})(?![\d.,]*\s*(?:год|лет|мес|г\b|%|верс))(?:\s|$|[,.!?])')
ONE = re.compile(r'\b(?:одн[оау]\w*\s+(?:рабоч\w*\s+мест\w*|рабоч\w*\s+станци\w*|компьютер\w*|пк|пользовател\w*|лицензи\w*|подключени\w*|устройств\w*)|один\s+(?:компьютер|пк|пользователь|ключ)|1\s+компьютер)')
TERM = (
    (36, re.compile(r'\b(?:3|три)\s*(?:года|лет)\b|36\s*мес')),
    (24, re.compile(r'\b(?:2|два)\s*(?:года|лет)\b|24\s*мес')),
    (12, re.compile(r'\b(?:на\s+)?(?:1\s+|один\s+)?год\b|годов\w*|12\s*мес|на\s+год|one-year|1-year|annual|\byear\b')),
    (1, re.compile(r'\bна\s+месяц\b|\b1\s*мес')),
    (0, re.compile(r'бессроч\w*|навсегда|вечн\w*')),
)
RENEWAL = re.compile(r'продлен\w*|продлить|продлева\w*|renewal')
EDU = re.compile(r'школ\w*|образоват\w*|учебн\w*|академ\w*|education|вуз\w*|университет\w*')
PERSON = re.compile(r'физ\w*\s*лиц|физлиц|физик|просто человек|для дома|домашн')
CLOSING = re.compile(r'^\s*(?:ок|окей|ok|хорошо|понял\w*|ясно|спасибо|благодарю|жаль|ждем|ждём|жду\s+ответа|буду\s+ждать|принято|договорились|супер|отлично|наш[её]л\w*|вс[её]\s+наш[её]л\w*|разобрал\w*)'
                     r'(?:[\s,.!]+(?:спасибо|благодарю|ждем|ждём|жду\s+ответа|понял\w*|оформлю\s+на\s+сайте|ок|большое|за\s+помощь|тогда|наш[её]л\w*))*[\s.!)]*$')
CHEAPER = re.compile(r'дешевл\w*|подешевле|самы[йе]\s+деш\w*|бюджетн\w*|недорог\w*')
# «а word и excel там есть?», «что входит в пакет» — вопрос о составе текущего товара, а не поиск нового
COMPOSITION = re.compile(r'\bтам\s+есть\b|\bесть\s+ли\s+(?:там|в\s+н\w*)\b|\bвход(?:ит|ят)\b|\bвключ\w*|\bв\s+состав\w*|\bв\s+комплект\w*|\bсостав\s+(?:пакета|лицензии)')
INSIST = re.compile(r'\bименно\b|только\s+(?:его|её|ее|этот|эту)|другой\s+не\s+(?:нужен|подходит)')
ANALOG_ASK = re.compile(r'аналог\w*|вместо|замен\w*|что\s+(?:есть|ещё|еще)\s+(?:вместо|похож)|что\s+есть\s+для|что\s+есть\??$|отечествен\w*\s+(?:аналог|сервер|вариант)|рассмотрим\s+отечествен')
PER_UNIT = re.compile(r'на\s+одном|на\s+1\s+(?:рабоч|пк|пользоват|компьют|ip|устройств)|за\s+1\s|цена\s+за|однопользоват|per\s+seat|rutoken|'
                      r'электронн\w+\s+ключ|на\s+1\s+рабочее|1\s+рабочее\s+место|solo|standard$|на\s+1\s+год\)|ip-адрес')
EDITION_WORDS = ('standard', 'professional', 'pro', 'corporate', 'business', 'lite', 'advanced', 'basic', 'базов', 'расширен',
                 'стандарт', 'плюс', 'смоленск', 'орел', 'воронеж', 'сетев', 'фстэк', 'solo', 'home', 'для дома', 'бизнес')


def aliased(text: str) -> str:
    t = normalize(text)
    for pattern, repl in ALIASES:
        t = re.sub(pattern, repl, t)
    return t


def words(text: str) -> list[str]:
    t = aliased(text)
    t = re.sub(r'<script\b.*?</script>|\[[^\]]{0,30}\]|<[^>]{1,40}>', ' ', t)           # [тел], [email] из обезличенной выгрузки
    t = re.sub(r'\b(?:не|без|кроме)\s+(?!нужн|надо|ндс|сч)[^\W\d_]+', ' ', t)  # «не гост», «не se» — исключение, а не запрос
    t = re.sub(r'\S+@\S+|https?://\S+', ' ', t)
    t = re.sub(ORG_NAME, ' ', t)                       # «ООО «Вектор»» — покупатель, а не товар
    t = re.sub(r'\b(?:инн|кпп|огрн\w*|бик|р/?с)\b[\s:=№]*\d*', ' ', t)
    out = []
    for w in re.findall(r'[^\W_]+(?:[.\-][^\W_]+)*', t):
        if w in STOP or (len(w) < 2 and not w.isdigit()):
            continue
        out.append(w)
    return list(dict.fromkeys(out))


NUMBER_WORDS = {
    'одну': 1, 'одна': 1, 'один': 1, 'одно': 1, 'две': 2, 'два': 2, 'три': 3, 'четыре': 4, 'пять': 5, 'шесть': 6, 'семь': 7,
    'восемь': 8, 'девять': 9, 'десять': 10, 'двадцать': 20, 'тридцать': 30, 'пятьдесят': 50, 'сто': 100,
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}
NUMBER_WORD = re.compile(r'(?<![^\W_])(' + '|'.join(NUMBER_WORDS) + r')(?![^\W_])')
QTY_EN = re.compile(r'\b([1-9]\d{0,4})\s+(?:[a-z0-9-]+\s+){0,4}(?:licen[cs]es?|seats?|users?|devices?|pcs)\b')
CORRECTION = re.compile(r'(?<![\d.,])([1-9]\d{0,4})\s*,?\s*а\s+не\s+\d+')


def digits(text: str) -> str:
    """«три штуки» → «3 штуки», «two licenses» → «2 licenses». «один год» → «1 год» срок не меняет."""
    return NUMBER_WORD.sub(lambda m: str(NUMBER_WORDS[m.group(1)]), normalize(text))


def quantity(text: str) -> int | None:
    if ONE.search(normalize(text)):
        one = True
    else:
        one = False
    t = digits(text)
    m = CORRECTION.search(t) or QTY.search(t) or QTY_EN.search(t)
    if m and not (one and m.group(1) == '1'):
        return int(m.group(1))
    if one:
        return 1
    m = QTY_BARE.search(t)
    return int(m.group(1)) if m else None


def term(text: str) -> int | None:
    t = normalize(text)
    for months, pattern in TERM:
        if pattern.search(t):
            return months
    return None


def slots_from(text: str, state: dict):
    excl = [aliased(w).split()[0] for w in EXCLUDE.findall(normalize(text)) if not EXCLUDE_SKIP.match(w)]
    if excl:
        state['g_exclude'] = list(dict.fromkeys(state.get('g_exclude', []) + excl))[:6]
    q = quantity(text)
    if q:
        state['quantity'] = q
    m = term(text)
    if m is not None:
        state['g_term'] = m
    t = normalize(text)
    if RENEWAL.search(t):
        state['g_renewal'] = True
    elif re.search(r'\bнов\w*\s+лиценз|\bнов(?:ая|ую)\b|раньше не было', t):
        state['g_renewal'] = False
    if EDU.search(t):
        state['g_edu'] = True
    if PERSON.search(t):
        state['g_person'] = True
    eds = [w for w in EDITION_WORDS if re.search(r'\b' + re.escape(w), aliased(text))]
    if eds:
        state['g_edition'] = eds


# ── поиск семьи товара ───────────────────────────────────────────────────────
PINNED = (
    (re.compile(r'windows\s*11\s*pro'), '380385'),
    (re.compile(r'office.{0,40}(?:дома|домашн)\w*\s+и\s+бизнес'), '473582'),  # «для дома и бизнеса» — это не «для дома»
    (re.compile(r'office.{0,40}(?:дома|домашн|для\s+учеб)|(?:дома|домашн).{0,40}office'), '473568'),
    (re.compile(r'office(?!\s*365).{0,60}(?:бизнес|для\s+офиса|юр\w*|организац|компан)|(?:microsoft|майкрософт)\s+office(?!\s*365)'), '473582'),
)
FLAGSHIP = {'410137', '380385', '473568', '473582', '19576'}
SKU = re.compile(r'\b([a-z]{2,4}\d{3,}[a-z0-9]*)')


ENDINGS = sorted('иями ями ами ого его ому ему ыми ими ией ов ев ей ой ом ем ам ям ах ях ую юю ая яя ое ее ые ие ых их ым им ий ый ия ию а я ы и у ю е о ь'.split(),
                 key=len, reverse=True)


def stem(word: str) -> str:
    """Лёгкая основа русского слова: одно окончание, основа не короче 5 букв. Латиница и короткие слова — как есть."""
    if len(word) < 6 or not re.fullmatch(r'[а-я]+', word):
        return word
    for e in ENDINGS:
        if word.endswith(e) and len(word) - len(e) >= 5:
            return word[:-len(e)]
    return word


def _match_tokens(tokens: list[str]) -> str:
    parts = []
    for w in tokens[:10]:
        w = w.replace('"', '')
        parts.append(f'"{w}"*' if len(w) >= 3 and not w.isdigit() else f'"{w}"')
    return ' OR '.join(parts)


def _family(db, family_id):
    return [view(r) for r in db.execute('SELECT * FROM products WHERE family=? ORDER BY available DESC, price_kopecks', (family_id,)).fetchall()]


ACCESSORY = re.compile(r'техподдерж|техническ\w* поддерж|сертификат на|дистрибутив|media\s*pack|медиа|course|курс|ask the analyst|замена ключа|замен\w*\s+(?:\w+\s+){0,2}ключ|документац|обучени|экзамен|консультац|внедрени|услуг')
LICENSE_WORDS = re.compile(r'работ|подпис|укэп|эцп|самозанят|бессроч|лиценз|годов|год|компьютер|рабоч|мест|пользоват|сотрудник|устройств|счет|кп|стоимост|цен|ткп|базов|юр|физ')
BRAND_DEFAULT = {'kaspersky': '413710', 'криптопро': '410137', 'криптоарм': '421003'}  # «касперский», «крипто про» без уточнений — основной продукт
GENERIC = re.compile(r'standard|стандарт|business|бизнес|академ|образоват|server|сервер|lite|linux|corporate|professional|pro|enterprise|edition|license|home')
EDITION_FOLLOWUP = re.compile(r'(?:standard|стандарт\w*|professional|профессиональн\w*|расширенн\w*|базов\w*)'
                              r'(?:\W+(?:нов\w*\s+лицензи\w*|продлени\w*))?\W*')


def _only_for(name: str, word: str) -> bool:
    """Слово встречается в названии только как «для X» / «for X»."""
    spots = [m.start() for m in re.finditer(r'(?<![^\W_])' + re.escape(word), name)]
    return bool(spots) and all(re.search(r'(?:^|\W)(?:для|for|under|под|версия|платформ\w*|ос)\W(?:\w+\W){0,2}$', name[:i]) for i in spots)


# Русские написания брендов, которых нет в названиях каталога (там латиница): нужны для исправления опечаток
ORG_NAME = re.compile(r'(?<![^\W_])(?:ооо|ао|пао|зао|оао|ип|гбу|мбу|фгбу|гку|мку|ано|нко)\s+(?:[«"][^»"]{1,60}[»"]|[^\W\d_]+(?:\s+[^\W\d_]\.?){0,3})')
BRAND_SPELLINGS = '''касперский касперского касперскому майкрософт мультифактор грандсмета гранд-смета фотошоп виндовс
анидеск энидеск криптопро криптоарм юзергейт нанокад термидеск мовавика рутокен линукс астра
оригиналы оригинал бухгалтерские закрывающие документы доставка доставлены скачать реквизиты аналог аналоги аналогичный
коммерческое предложение счет-оферта отсрочка постоплата продление бессрочная бессрочные'''.split()  # и слова справки — чтобы опечатка в вопросе не уводила в товар
_VOCAB: dict[str, dict[str, list[str]]] = {}


def _vocab(db: sqlite3.Connection) -> dict[str, list[str]]:
    """Слова из названий и производителей каталога, по первой букве. Строится один раз на файл каталога."""
    key = db.execute('PRAGMA database_list').fetchone()[2] + str(db.execute('SELECT count(*) FROM products').fetchone()[0])
    if key not in _VOCAB:
        seen = set(BRAND_SPELLINGS)
        for name, vendor in db.execute('SELECT name, vendor FROM products'):
            seen.update(w for w in re.findall(r'[^\W\d_]{4,}', normalize(f'{name} {vendor}')))
        buckets: dict[str, list[str]] = {}
        for w in seen:
            buckets.setdefault(w[0], []).append(w)
        _VOCAB.clear()
        _VOCAB[key] = buckets
    return _VOCAB[key]


def _one_edit(a: str, b: str) -> bool:
    """Расстояние Дамерау — Левенштейна ровно 1."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = next((k for k in range(len(a)) if a[k] != b[k]), len(a))
    if len(a) < len(b):
        return a[i:] == b[i + 1:]
    return a[i + 1:] == b[i + 1:] or (i + 1 < len(a) and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:])


def fix_typos(db: sqlite3.Connection, text: str) -> str:
    """«касепрский» → «касперский», «photohsop» → «photoshop»: только слова от 6 букв, которых нет ни в каталоге, ни в словаре."""
    vocab = _vocab(db)
    out = normalize(text)
    for w in set(re.findall(r'[^\W\d_]{6,}', out)):
        bucket = vocab.get(w[0], [])
        if w in STOP or w in bucket or any(re.fullmatch(p, w) for p, _ in ALIASES):
            continue
        near = [c for c in difflib.get_close_matches(w, [c for c in bucket if abs(len(c) - len(w)) <= 1], n=5, cutoff=0.8)
                if _one_edit(w, c)]  # ровно одна правка: переставлены, пропущена, лишняя или заменена буква
        if near:
            out = re.sub(r'(?<![^\W_])' + re.escape(w) + r'(?![^\W_])', near[0], out)
    return out


def find_family(db: sqlite3.Connection, tokens: list[str], text: str = '', ranking: list | None = None):
    fixed = fix_typos(db, text) if text else text
    if fixed != normalize(text):
        text, tokens = fixed, words(fixed)
    """Лучшая семья товара по словам клиента: редкие слова весят больше (IDF), слова, которых нет в каталоге, не мешают.
    Возвращает (строки семьи, уверенность 0..1, совпавшие слова, слова, которых нет в каталоге)."""
    q = aliased(text)
    if re.search(r'kaspersky endpoint security', q) and not re.search(r'расширен|плюс|plus|total|оптимал|cloud|облач|edr|expert|эксперт|advanced|select', q):
        row = db.execute("SELECT family FROM products WHERE id='413710'").fetchone()
        if row:
            return _family(db, row['family']), 1.0, ['pinned'], []
    for pattern, offer_id in PINNED:
        if pattern.search(q):
            row = db.execute('SELECT family FROM products WHERE id=?', (offer_id,)).fetchone()
            if row:
                return _family(db, row['family']), 1.0, ['pinned'], []
    for sku in SKU.findall(q):
        row = db.execute("SELECT family FROM products WHERE lower(sku) LIKE ? ORDER BY available DESC LIMIT 1", (sku + '%',)).fetchone()
        if row:
            return _family(db, row['family']), 1.0, [sku], []
    if not [w for w in tokens if not w.isdigit()]:
        return [], 0.0, [], []
    brand_words = {out for pat, outs in ALIASES for out in outs.split() if not out.isdigit()}
    orig = {}
    for w in tokens[:10]:
        orig.setdefault(w if w in brand_words else stem(w), w)
    total = db.execute('SELECT count(*) FROM products').fetchone()[0] or 1
    idf, unknown = {}, []
    for w in orig:
        try:
            df = db.execute('SELECT count(*) FROM product_search WHERE product_search MATCH ?', (_match_tokens([w]),)).fetchone()[0]
        except sqlite3.OperationalError:
            df = 0
        if df:
            idf[w] = math.log(total / df)
        else:
            unknown.append(orig[w])
    if not idf:
        return [], 0.0, [], unknown
    if any(orig[w] in unknown and w in brand_words and not GENERIC.fullmatch(w) and not w.isdigit() for w in orig):
        return [], 0.0, [], unknown   # назван бренд, которого нет в каталоге: не подменяем товаром по остальным словам
    rows = db.execute('''
        SELECT p.*, bm25(product_search, 10.0, 6.0, 1.0, 0.1) AS rank
        FROM product_search JOIN products p ON p.rowid=product_search.rowid
        WHERE product_search MATCH ? ORDER BY rank LIMIT 600''', (_match_tokens(list(idf)),)).fetchall()
    latin = [w for w in idf if re.fullmatch(r'[a-z][a-z0-9.\-]*', w) and len(w) >= 3 and not GENERIC.fullmatch(w)]
    brands = brand_words & set(idf)
    must = [w for w in idf if w in brands and not GENERIC.fullmatch(w)]
    rest = [w for w in idf if w not in must]
    if must and rest:
        rows = list(rows) + db.execute('''
            SELECT p.*, bm25(product_search, 10.0, 6.0, 1.0, 0.1) AS rank
            FROM product_search JOIN products p ON p.rowid=product_search.rowid
            WHERE product_search MATCH ? ORDER BY rank LIMIT 300''', (f'({_match_tokens(must)}) AND ({_match_tokens(rest)})',)).fetchall()
    qn = aliased(text)
    pairs = [(a, b) for a, b in zip(list(idf), list(idf)[1:])]
    flagship = {r['family'] for r in db.execute(f"SELECT family FROM products WHERE id IN ({','.join('?' * len(FLAGSHIP))})", tuple(FLAGSHIP))}
    rows = list(rows) + db.execute(f"SELECT p.*, 0 AS rank FROM products p WHERE id IN ({','.join('?' * len(FLAGSHIP))})", tuple(FLAGSHIP)).fetchall()
    best, best_score, best_hit = None, 0.0, []
    hits_by_id = {}
    hit_of = lambda r: hits_by_id.get(r['id'], [])  # noqa: E731
    for row in rows:
        name = normalize(row['name'] + ' ' + row['vendor'])
        hit = [w for w in idf if re.search(r'(?<![^\W_])' + re.escape(w), name)]
        rare_latin = max(latin, key=idf.get) if latin else None
        if not hit or (rare_latin and rare_latin not in hit and sum(w in hit for w in latin) < 3) or (must and not any(w in hit for w in must)):
            continue
        if any(re.search(re.escape(w) + r'\W+(?:server|сервер)', qn) and not re.search(re.escape(w) + r'\W+(?:\w+\W+)?server', name) for w in must):
            continue  # «windows server» — не любой товар со словом windows
        if must and all(_only_for(name, w) for w in must if w in hit):
            continue  # «Kaspersky для Microsoft Office 365» — это не сам Office
        score = sum(idf[w] for w in hit)
        score += sum(idf[a] + idf[b] for a, b in pairs if re.search(re.escape(a) + r'\w*\W{1,3}' + re.escape(b), name))
        first = min(name.find(w) for w in hit)
        score += 0.6 if row['available'] and row['price_kopecks'] else 0
        score += 0.4 if 0 <= first < 40 else 0
        score += 2.0 if row['family'] in flagship else 0
        acc = ACCESSORY.search(name)
        if acc and not ACCESSORY.search(qn):
            score -= 1.0  # техподдержка, курсы, ключи, дистрибутивы — только если о них спросили
        if ranking is not None:
            ranking.append((score, row['family']))
        if score > best_score:
            best, best_score, best_hit = row, score, hit
            hits_by_id[row['id']] = hit
    if best is not None:
        extra = [w for w in hit_of(best) if w not in brand_words and not GENERIC.fullmatch(w) and not w.isdigit() and not LICENSE_WORDS.match(w)]
        brand = next((b for b in BRAND_DEFAULT if b in idf and b in hit_of(best)), None)
        if brand and not extra:
            row = db.execute('SELECT family FROM products WHERE id=?', (BRAND_DEFAULT[brand],)).fetchone()
            if row:
                return _family(db, row['family']), 0.9, [brand], unknown
    if best is None:
        # названный товар не нашёлся: латинские слова запроса считаем названием того, чего нет в каталоге
        named = [w for w in idf if w in must]
        return [], 0.0, [], [orig.get(w, w) for w in orig if orig[w] in unknown or (named and w in idf and re.fullmatch(r'[a-z][a-z0-9.\-]{2,}', w))]
    top = max(idf, key=idf.get)
    confidence = min(0.9, sum(idf[w] for w in best_hit) / sum(idf.values()))
    name = normalize(best['name'] + ' ' + best['vendor'])
    strong = any(idf[w] >= 5 and 0 <= name.find(w) < 40 for w in best_hit) or any(w in best_hit for w in latin)
    if top in best_hit or strong:
        confidence = max(confidence, 0.6)
    words_hit = [w for w in best_hit if not w.isdigit() and not LICENSE_WORDS.match(orig.get(w, w)) and not GENERIC.fullmatch(w)]
    named = [w for w in best_hit if (w in brand_words and not GENERIC.fullmatch(w)) or (re.fullmatch(r'[a-z][a-z0-9.\-]{3,}', w) and not GENERIC.fullmatch(w) and 0 <= normalize(best['name']).find(w) < 60)]
    if (any(idf[w] >= 6 and w in words_hit for w in best_hit) and (named or len(words_hit) >= 2)) or 'pinned' in best_hit:
        confidence = max(confidence, 0.95)
    if any(w in brand_words and not GENERIC.fullmatch(w) for w in best_hit):
        confidence = max(confidence, 0.6)   # бренд назван и найден — показываем, даже если остальные слова о задаче («для планшетов»)
    # Порог «не уверен — не предлагаю» (CME 295, лекция 6: отказ от слабой выдачи лучше случайного товара).
    # Без названия (бренда или латиницы в начале названия) товар должен покрывать хотя бы 45 % смысловых слов запроса.
    content = [w for w in idf if not w.isdigit() and not LICENSE_WORDS.match(orig[w]) and not GENERIC.fullmatch(w)]
    cover = sum(idf[w] for w in best_hit if w in content) / (sum(idf[w] for w in content) or 1) if content else 1.0
    vocab = _vocab(db)
    absent = [orig[w] for w in latin if w not in best_hit and len(w) >= 4 and w not in vocab.get(w[0], ())]
    unknown_latin = [w for w in unknown + absent if re.fullmatch(r'[a-z]{4,}', w)]  # слово-название, а не артикул
    head_hit = any(0 <= normalize(best['name']).find(w) < 40 for w in best_hit if not w.isdigit() and not GENERIC.fullmatch(w))
    if unknown_latin and not (set(best_hit) & brand_words) and (not head_hit or all(re.fullmatch(r'[a-z0-9.\-]+', w) for w in best_hit)):
        return [], 0.0, [], unknown + absent   # «rupost в docker»: названного товара нет в названиях каталога, «docker» — не товар
    if not named and (cover < 0.45 or not content):   # только общие слова («сервер», «пользователей») — не товар
        confidence = min(confidence, 0.4)
    return _family(db, best['family']), confidence, [orig.get(w, w) for w in best_hit], unknown


def per_unit(offer: dict) -> bool:
    return bool(PER_UNIT.search(normalize(offer['name']))) or offer.get('max_users') == 1


def units_for(offer: dict, qty: int | None) -> int | None:
    if not qty:
        return 1
    sku = (offer.get('sku') or '').upper()
    family = next((prefix for prefix in KASPERSKY_FAMILIES if sku.startswith(prefix)), None)
    if family:
        tier = kaspersky_tier(qty)
        return qty if tier and sku[len(family):].startswith(tier) else None
    lo, hi = offer.get('min_users'), offer.get('max_users')
    if hi and hi > 1:
        return 1 if (lo or 1) <= qty <= hi else None
    m = re.search(r'(\d{1,5})\s+(?:объект|пользовател|устройств|узл|ip)', normalize(offer['name']))
    if m and int(m.group(1)) > 1:
        return 1 if qty <= int(m.group(1)) else None
    return qty if per_unit(offer) or qty == 1 else qty


def offer_term(offer: dict) -> int | None:
    n = normalize(offer['name'])
    if offer.get('term_months'):
        return offer['term_months']
    if 'бессроч' in n:
        return 0
    m = re.search(r'(\d)\s*(?:год|лет)', n)
    if m:
        return 12 * int(m.group(1))
    if re.search(r'1\s*год|на\s+год|годов', n):
        return 12
    return None


def choose(family: list[dict], state: dict, text: str) -> list[dict]:
    """Отбор позиций семьи по условиям клиента. Чем меньше осталось, тем точнее понят запрос."""
    offers = [o for o in family if o['available'] and o['price_kopecks']]
    if not offers:
        return []
    q = aliased(text + ' ' + state.get('g_query', ''))

    def keep(pred):
        nonlocal offers
        narrowed = [o for o in offers if pred(o)]
        if narrowed:
            offers = narrowed

    if re.search(r'\b(?:1|одн\w*)\s+устройств', q):  # «на одно устройство» — не пакет на 5 устройств
        keep(lambda o: re.search(r'(?<!\d)1\s+устройств', normalize(o['name'])) is not None)
    for x in state.get('g_exclude', []):  # «без Mobile», «не ГОСТ»
        keep(lambda o, x=x: x not in aliased(o['name']))

    if state.get('g_term') is not None:
        keep(lambda o: offer_term(o) == state['g_term'])
    if state.get('g_renewal') is not None:
        keep(lambda o: bool(re.search(r'продлен|renewal', normalize(o['name']))) == state['g_renewal'])
    else:
        keep(lambda o: not re.search(r'продлен|renewal|миграц|upgrade', normalize(o['name'])))
    keep(lambda o: bool(EDU.search(normalize(o['name']))) == bool(state.get('g_edu')))
    for ed in state.get('g_edition', []):
        keep(lambda o, ed=ed: ed in aliased(o['name']))
    for w in re.findall(r'\b\d+(?:\.\d+)?\b', q):
        if w not in {str(state.get('quantity'))}:
            keep(lambda o, w=w: re.search(r'(?<![\d.])' + re.escape(w) + r'(?![\d])', normalize(o['name'])) is not None)
    if state.get('quantity'):
        keep(lambda o: units_for(o, state['quantity']) is not None and (not o.get('max_users') or o['max_users'] >= state['quantity']))
    keep(lambda o: not re.search(r'медиа|дистрибутив|документац|cross-?grade|кросс|additional|bundle|add-?on|дополнительн|техподдержк|техническ\w+ поддержк', normalize(o['name'])))
    if CHEAPER.search(normalize(text)):
        return sorted(offers, key=lambda o: o['price_kopecks'])[:1]
    asked = set(words(state.get('g_text', '') + ' ' + text))

    def rank(o):
        name = normalize(o['name'])
        overlap = sum(1 for w in asked if re.search(r'(?<![^\W_])' + re.escape(w), name))
        odd = bool(re.search(r'иностран|обновлени|upgrade|для\s+версии', name)) and not state.get('g_renewal')
        return (-(o['id'] in FLAGSHIP), odd, -overlap, o['price_kopecks'])
    return sorted(offers, key=rank)


def money(kopecks: int) -> str:
    rub, kop = divmod(int(round(kopecks)), 100)
    text = f'{rub:,}'.replace(',', ' ')
    return f'{text},{kop:02d} ₽' if kop else f'{text} ₽'


def price_line(offer: dict, qty: int | None, discount: int = 0, units: int | None = None) -> str:
    units = units or units_for(offer, qty) or 1
    total = offer['price_kopecks'] * units
    line = f'{offer["name"]} — {money(offer["price_kopecks"])}'
    if units > 1:
        line += f' × {units} = {money(total)}'
    if discount:
        line += f'; со скидкой {discount}% — {money(discounted(total, discount))}'
    return line + (f'. Карточка: {offer["url"]}' if offer.get('url') else '')


# ── справка без товара ────────────────────────────────────────────────────────
FAQ = (
    (re.compile(r'\bндс\b'), 'Цены в каталоге Softline Store указаны с НДС, если в карточке не сказано иное. Счёт для юрлица выставляется с НДС; '
                              'точную ставку по позиции менеджер укажет в КП.'),
    (re.compile(r'эдо|бух\w*\s+документ|закрывающ|оригинал\w*|упд|акт\w*\s+(?:и|выполн)'),
     'По заказам юрлиц бухгалтерские документы (счёт, УПД или акт) высылают по почтовому адресу из заказа; при электронной доставке — Почтой '
     'России в течение 7 рабочих дней после отправки ключа. Через ЭДО — заявка менеджеру или на edo@softline.com с оператором и реквизитами '
     '(https://store.softline.ru/delivery_info/#q7).'),
    (re.compile(r'как\s+получ\w*\s+(?:коммерческ|кп)'), 'Соберу черновик КП по каталогу: напишите продукт, количество и срок. Какой продукт нужен?'),
    (re.compile(r'(?<!\w)(?!.*дистрибутив)(?:скача\w*)|как\s+получ\w*\s+(?:ключ|лиценз|программ)|ключ\w*.{0,30}(?:приход|прид|получ)|после оплаты|доставк\w*'),
     'Электронные лицензии приходят письмом на почту из заказа в любой регион; срок указан в карточке товара — от 5 минут до 30 рабочих дней. '
     'Коробки и оборудование: 2–3 рабочих дня по Москве и области, 2–7 рабочих дней по России после оплаты; стоимость доставки считается '
     'при оформлении заказа (https://store.softline.ru/delivery_info/#q9).'),
    (re.compile(r'(?:физ\w*\s*лиц|физлиц|просто человек|частн\w+\s+лиц|не предприниматель)'),
     'Да, физическое лицо может купить на сайте store.softline.ru с оплатой картой; документы оформляются на покупателя. '
     'Для юрлица — по счёту с реквизитами.'),
    (re.compile(r'\bип\b|предпринимател'),
     'Да, ИП может купить: для счёта и КП нужны ФИО или название ИП и ИНН из 12 цифр, КПП у ИП нет.'),
    (re.compile(r'для\s+юр\w*\s+лиц|на\s+юр\w*\s+лиц'),
     'Для юрлица счёт и документы оформляются на организацию по реквизитам: название, ИНН и КПП.'),
    (re.compile(r'сколько\s+ждать|сроки?\s+ответ\w*|когда\s+ответ\w*|как\s+долго'),
     'Менеджер отвечает в рабочее время, обычно в течение 1–2 часов; ответ придёт в этот чат.'),
    (re.compile(r'обновлен\w*.{0,40}(?:платн|бесплатн|верси)|верси\w*.{0,30}обновлен'),
     'Переход на новую версию обычно оформляется отдельной лицензией или обновлением; условия по вашему продукту уточнит менеджер.'),
    (re.compile(r'реестр\w*'), 'Номер записи в едином реестре российского ПО для закупочной документации подтвердит менеджер по выбранной позиции.'),
    (re.compile(r'подтвержд\w*\s+(?:лиценз|легальн|покупк)|проверяющ\w*\s+орган|какой-?\s?то\s+документ'),
     'Юрлицу по оплаченному заказу приходят закрывающие документы (УПД или акт) с названием программы; вместе с письмом-лицензией они '
     'подтверждают законную покупку. В счёте указывается наименование позиции из каталога.'),
    (re.compile(r'дистрибутив'), 'Дистрибутив обычно скачивается бесплатно с сайта производителя; в цену лицензии входит право использования.'),
    (re.compile(r'навсегда|бессрочн\w*\s*\?|это\s+бессрочн'), None),
)
# ── после покупки и справка магазина: ответы по статьям store.softline.ru/delivery_info (прочитано 27.11) ──────────
HELP = 'https://store.softline.ru/delivery_info/'
SUPPORT_TOPICS = (
    # (шаблон, ответ, причина передачи менеджеру или None)
    (re.compile(r'(?:как\s+(?:сформировать|получить|выписать)|где\s+(?:взять|найти|скачать))\s+(?:\w+\s+){0,2}сч[её]т|сч[её]т\w*\s+(?:на\s+оплату\s+)?(?:не\s+приш|отсутств|нет\s+на\s+почт|не\s+приход)'),
     'Счёт на оплату для юрлица и ИП формируется при оформлении заказа в корзине на store.softline.ru и доступен в личном кабинете, '
     f'а копия приходит письмом на почту из заказа — проверьте папку «Спам» ({HELP}#q5). '
     'Если счёта нет ни в кабинете, ни в «Спаме», напишите сюда или нажмите «Позвать оператора» — передам менеджеру.', None),
    (re.compile(r'не\s+(?:могу|получается)\s+скачать\s+дистрибутив|ссылк\w*\s+(?:не\s+открыва|для\s+установк\w*\s+не|на\s+скачивани\w*\s+не)|не\s+приход\w*\s+ссылк\w*\s+(?:для\s+установк|на\s+скачиван)'),
     'Ссылку на скачивание дистрибутива проверьте в письме о заказе (и в папке «Спам») и в личном кабинете Softline; если ссылка не открывается, '
     'попробуйте другой браузер или режим инкогнито. Базовая техподдержка Softline: store.support@softline.com, +7 (495) 128-41-36 '
     f'({HELP}#q13). Если не помогло, напишите сюда — передам менеджеру.', None),
    (re.compile(r'плат[её]ж\w*\s+прош[её]л|заказ\s+(?:в\s+кабинете\s+)?не\s+оплачен|оплат\w*\s+прошл\w*.{0,40}не\s+отображ'),
     'Поступление безналичного платежа обычно отображается в личном кабинете Softline в течение 1–2 рабочих дней после оплаты '
     f'({HELP}#q5). Если срок уже прошёл, пришлите номер заказа и дату платежа (или платёжное поручение) — передам менеджеру для сверки.', None),
    (re.compile(r'не\s+(?:\w+\s+){0,2}активир\w*|ошибк\w*\s+(?:при\s+)?(?:активир|активац)|(?:помогите|как)\s+(?:\w+\s+)?активир'
                r'|активаци\w*\s+(?:\w+\s+){0,3}(?:не\s|ошибк)|ключь?\w*\s+(?:\w+\s+){0,2}(?:не\s+(?:п[ао]дх|принима|работ|актив)|недейств|уже\s+(?:использ|активир))'
                r'|(?:недействител|неверн)\w*\s+(?:ключ|лиценз|серийн)|лиценз\w*\s+недейств|0x[0-9a-f]{6,8}'),
     'Проблему с активацией разберёт менеджер по вашему заказу: у меня нет доступа к заказам. Пришлите сюда номер заказа и текст ошибки '
     '(можно снимок экрана) — так ответят быстрее. Базовая техподдержка Softline бесплатна 3 месяца после покупки: store.support@softline.com, '
     f'+7 (495) 128-41-36, по рабочим дням с 9 до 18 МСК ({HELP}#q13). ', 'activation_problem'),
    (re.compile(r'статус\w*\s+(?:\w+\s+){0,2}заказ|(?:где|когда)\s+(?:\w+\s+){0,2}(?:мой|наш)\s+заказ|состояни\w*\s+(?:\w+\s+)?заказ'),
     f'Статус заказа виден в личном кабинете Softline — ссылка на него есть в письме о заказе ({HELP}#q2). У меня нет доступа к заказам, '
     'поэтому передаю вопрос менеджеру; пришлите номер заказа. ', 'order_question'),
    (re.compile(r'не\s+(?:приш|приход|получ|приезж)\w*\s+(?:\w+\s+)?(?:письм|ключ|лиценз|заказ)|(?:письм|ключ|лиценз|заказ)\w*\s+(?:\w+\s+){0,3}не\s+(?:приш|приход|получ|доставл)'
                r'|оплатил\w*\s+(?:\w+\s+){0,4}(?:ключ|лиценз|письм)\w*\s+(?:так\s+и\s+)?(?:нет|не\s)|(?:ключ|лиценз)\w*\s+(?:до\s+сих\s+пор\s+|так\s+и\s+|всё\s+ещё\s+|все\s+еще\s+)?нет\b'),
     'Электронные ключи отправляют по рабочим дням с 9 до 21 МСК, срок указан в карточке товара — от 5 минут до 30 рабочих дней '
     f'({HELP}#q9). Проверьте папку «Спам». Чтобы проверить ваш заказ, передаю вопрос менеджеру; пришлите номер заказа. ', 'order_question'),
    (re.compile(r'возврат\w*|верн(?:уть|ите|ете)\s+(?:\w+\s+)?(?:деньг|товар|лиценз|оплат)|деньг\w*\s+(?:\w+\s+)?верн|отказ\w*\s+от\s+(?:заказ|покупк|товар)'),
     'По правилам магазина электронные лицензии возврату не подлежат: ключ генерируется под покупателя. Коробки и оборудование можно вернуть до '
     f'получения или в течение 7 дней после, если не вскрыта упаковка ({HELP}#q15). Ваш случай оформит менеджер — передаю; пришлите номер заказа. ',
     'order_question'),
    (re.compile(r'(?:забыл|восстанов|сброс|смен|не\s+помн|поменя)\w*\s+(?:\w+\s+)?парол|парол\w*\s+(?:от|для|к)\s+(?:входа\s+(?:в|на)\s+)?(?:личн|кабинет|аккаунт|учетн|учётн|сайт|магазин)'
                r'|не\s+(?:могу|получается|удается|удаётся)\s+(?:войти|зайти)\s+(?:в|на)\s+(?:личн|кабинет|аккаунт|сайт|магазин|softline|софтлайн|store)'
                r'|не\s+(?:могу|получается|удается|удаётся)\s+(?:войти|зайти)\s*(?:[.?!]|$)|восстанов\w*\s+(?:доступ|аккаунт|учетн|учётн)'),
     'Восстановить пароль: на странице входа https://login.softline.ru нажмите «Забыли пароль?» (https://login.softline.ru/password) '
     'и укажите почту аккаунта. Письмо не пришло — проверьте «Спам»; если не помогло, нажмите «Позвать оператора».', None),
    (re.compile(r'не\s+(?:могу|получается|удается|удаётся)\s+(?:войти|зайти|запустить|установить)\s+(?:в\s+)?\w+|не\s+(?:запуска|устанавлива)ет\w*'
                r'|вылета\w*|после\s+обновлени\w*\s+(?:не\s|ошибк|слетел)|ошибк\w*\s+при\s+(?:установк|запуск|обновлени)'),
     'С работой установленной программы помогает техподдержка: базовая поддержка Softline бесплатна 3 месяца после покупки — '
     f'+7 (495) 128-41-36, store.support@softline.com, по рабочим дням с 9 до 18 МСК ({HELP}#q13). Если вопрос по заказу — нажмите «Позвать оператора».', None),
    (re.compile(r'доверенност\w*|форм\w*\s+м-?2\b'),
     'При получении товара юрлицу нужна доверенность на получение ТМЦ по форме М-2 и документ, удостоверяющий личность; ИП — печать или копия '
     'свидетельства о регистрации и копия паспорта, доверенному лицу ИП — оригинал доверенности М-2. Физлицу — паспорт '
     f'({HELP}#q11). Это для физической доставки товара.', None),
    (re.compile(r'как\s+(?:можно\s+)?(?:оплат|заплат)\w*|способ\w*\s+оплат|чем\s+(?:можно\s+)?оплат|оплат\w*\s+(?:через\s+)?сбп|sberpay'
                r'|(?:можно|можем|принимаете)\s+(?:ли\s+)?(?:\w+\s+)?оплат\w*\s+(?:\w+\s+)?(?:картой|карточкой|частями|наличн|по\s+сч[её]т)|оплат\w*\s+по\s+сч[её]ту?\s+для'),
     'Способы оплаты: банковский платёж по счёту (юрлица и ИП), банковская карта, СБП и SberPay (физлица), подарочный сертификат; '
     f'физлицам при получении коробок и оборудования — картой. Отсрочки нет, оплата заранее ({HELP}#q5).', None),
    (re.compile(r'(?:есть|какая|куда|контакт\w*|телефон\w*|почт\w*|бесплатн\w*)\s+(?:\w+\s+)?(?:техподдерж|техническ\w*\s+поддерж)|(?:техподдерж|техническ\w*\s+поддерж)\w*\s+после\s+покупк'
                r'|(?:обратиться|написать|позвонить|дозвониться)\s+(?:\w+\s+)?(?:в|к)\s+(?:тех)?поддержк|(?:тех)?поддержк\w*\s+(?:работа\w*|по\s+заказ|отвеча)'),
     'Базовая техподдержка бесплатна 3 месяца после покупки лицензионного ПО в Softline: +7 (495) 128-41-36, store.support@softline.com, '
     f'по рабочим дням с 9 до 18 МСК ({HELP}#q13).', None),
)


PURCHASED = re.compile(r'купил|приобрел|приобрёл|оплатил|заказал|(?:мой|наш|номер|по)\s+заказ|после\s+(?:покупк|оплат)|верн\w*\s+(?:\w+\s+)?деньг|деньг\w*\s+(?:\w+\s+)?верн|уже\s+(?:есть|получ)')
RETURN_ANSWER_ONLY = ('По правилам магазина электронные лицензии возврату не подлежат: ключ генерируется под покупателя. Коробки и оборудование '
                      f'можно вернуть до получения или в течение 7 дней после, если не вскрыта упаковка ({HELP}#q15). ')


def support_topic(t: str):
    """Вопрос после покупки или по справке магазина — раньше поиска товара: «купили Kaspersky, не активируется» не про покупку.
    Вопрос о правилах возврата до покупки («хочу купить Astra, какие условия возврата?») — ответ без передачи, продажа продолжается."""
    for pattern, answer, reason in SUPPORT_TOPICS:
        if pattern.search(t):
            if reason and 'возврат' in answer and not PURCHASED.search(t):
                return RETURN_ANSWER_ONLY + 'Продолжим подбор — какой продукт и на сколько мест нужен?', None
            return answer, reason
    return None


HANDOFF_FIRST = re.compile(r'ключ\w*\s+(?:найти|не\s+приш|потерял)|не\s+могу\s+найти|в\s+кабинете\s+не|сами.{0,20}посмотр|апгрейд|upgrade|'
                           r'история\s+заказ|в\s+\w+\s+20\d\d\s+(?:приобрет|покуп|купил)|возврат\w*|вернуть\s+деньги|'
                           r'письм\w*\s+с\s+ключ\w*\s+нет|не\s+приш\w*\s+(?:письм|ключ)|оплат\w*\s+прошл\w*.{0,60}(?:нет|не\s+приш)|'
                           r'то\s+же,?\s+что\s+(?:в|и)\s+прошл|прошл\w*\s+(?:покупк|заказ)')
PRICE_OVERRIDE = re.compile(r'(?:постав|сдела|укаж|напиш|впиш)\w*\s+(?:\w+\s+){0,4}цен\w*\s+(?:\w+\s+){0,2}\d|цен\w*\s+(?:в\s+)?\d[\d\s]*\s*(?:руб|₽|р\b)')
COMPLAINT = re.compile(r'(?:^|\s)(?:у\s+меня\s+)?жалоб\w*\b(?!\s+на\s+(?:цен|товар))|пожаловат\w*|нахамил\w*|хамств\w*|толку\s+(?:от\s+\w+\s+(?:\w+\s+)?)?нет|(?:напишу|пишу|подам|подаю|оставлю|направлю)\s+(?:\w+\s+)?(?:жалоб|претензи)\w*|безобрази\w*|не\s+получил\w*\s+ответ|ответ\w*\s+(?:на\s+\w+\s+)?вопрос\w*\s+не\s+получ|лояльност\w*\s+(?:к\s+клиент\w*\s+)?нет')
REQUEST_STATUS = re.compile(r'(?:запрос|заявк|обращени)\w*\s+(?:на\s+кп\s+|кп\s+)?(?:№\s*)?(\d{4,})|направлял\w*\s+(?:запрос|заявк)|отправлял\w*\s+(?:запрос|заявк)|'
                            r'когда\s+(?:можно\s+)?(?:будет\s+)?(?:получить|ждать)\s+(?:ответ|кп|счет)')
CARD_FOR_ORG = re.compile(r'(?:сво\w*|личн\w*)\s+(?:банковск\w*\s+)?карт\w*.{0,160}(?:организац|юр\w*\s*лиц|реквизит|библиотек|бухгалтер)|'
                          r'(?:организац|юр\w*\s*лиц|реквизит|бухгалтер).{0,160}(?:сво\w*|личн\w*)\s+(?:банковск\w*\s+)?карт|физ\w*\s*лиц\w*.{0,60}для\s+юр')
OFF_TOPIC = re.compile(r'(?:ничего\s+)?не\s+(?:хочу|буду|собираюсь)\s+(?:ничего\s+)?(?:купить|покупать|заказывать)|рецепт\w*\s+(?:блин|борщ|пирог|торт)|'
                       r'анекдот|погод\w*\s+в\s+')
EXCLUDE = re.compile(r'(?<![^\W_])(?:не|без|кроме|except|without)\s+([^\W\d_]{3,})')
EXCLUDE_SKIP = re.compile(r'нужн|надо|хочу|могу|можно|знаю|важн|лекци|сч[её]т|ндс|скидк|подпис|срок|продлен|обязательн|работа')
HANDOFF_ALWAYS = re.compile(r'\bтз\b|техническ\w+\s+задани|проект\w*\s+(?:контракт|договор)|44\s*-?\s*фз|223\s*-?\s*фз|тендер|госзакуп|'
                            r'аукцион|котировк|ключ\w*\s+(?:найти|не\s+приш|потерял)|не\s+могу\s+найти|в\s+кабинете\s+не|сами.{0,20}посмотр|'
                            r'апгрейд|upgrade|история\s+заказ|ранее\s+(?:приобрет|покуп)|в\s+\w+\s+20\d\d\s+(?:приобрет|покуп|купил)')


CATEGORIES = (
    (re.compile(r'(?:российск|отечествен)\w*\s+(?:ос\b|операционн)|операционн\w*\s+систем'), 'российские операционные системы',
     ('Российские операционные системы (Импортозамещение)',)),
    (re.compile(r'документооборот|\bсэд\b'), 'электронный документооборот',
     ('Программное обеспечение для ведения дел', 'Программное обеспечение для работы с документами', 'Программы для документооборота')),
    (re.compile(r'видеоконференц|видеосвяз|\bвкс\b|вебинар|онлайн[- ]?(?:совещ|встреч)|вместо\s+zoom|конференц-?связ'), 'видеоконференции и вебинары',
     ('Программное обеспечение для онлайн общения', 'Коммуникации (SaaS)')),
    (re.compile(r'почтов\w*\s+(?:сервер|систем)|корпоративн\w*\s+почт'), 'почтовые серверы', ('Почтовые клиенты', 'Почтовые утилиты')),
    (re.compile(r'антивирус|защит\w*\s+от\s+вирус'), 'антивирусы', ('Антивирусы для организаций',)),
    (re.compile(r'офисн\w*\s+(?:пакет|по\b|программ)|(?:российск|отечествен)\w*\s+(?:офис|office)|(?:офис|office)\w*.{0,60}(?:российск|отечествен)'),
     'российские офисные пакеты', ('Российское офисное ПО (Импортозамещение)', 'Другое офисное ПО')),
    (re.compile(r'удал[её]нн\w*\s+(?:доступ|подключ|рабоч|администр)'), 'удалённый доступ',
     ('Российские решения удаленного доступа (Импортозамещение)', 'Другие решения удаленного доступа')),
    (re.compile(r'восстановлени\w*\s+(?:данн|файл|информац)'), 'восстановление данных', ('Программное обеспечение для восстановления данных',)),
    (re.compile(r'резервн\w*\s+копирован|\bбэкап|\bbackup'), 'резервное копирование', ('Программное обеспечение для резервного копирования',)),
    (re.compile(r'виртуализац'), 'виртуализация', ('Российская виртуализация (Импортозамещение)', 'Программы для виртуализации')),
)
ESIGN = re.compile(r'электронн\w*\s+(?:цифров\w*\s+)?подпис|\bэцп\b|\bу?кэп\b|\bэп\b|подпис\w*\s+(?:на|в)\s+токен|'
                   r'(?:лиценз\w*|программ\w*)\s+для\s+(?:\w+\s+){0,2}электронн\w*\s+ключ|сдач\w*\s+(?:\w+\s+)?отчетност')


def category_reply(db, state: dict, text: str):
    """Клиент описал задачу без названия товара: по разделу каталога — до трёх товаров разных производителей с ценой из каталога."""
    ctx = normalize(state.get('g_cat_text', '') + ' ' + text)
    found = next(((pt, label, c) for pt, label, c in CATEGORIES if pt.search(ctx)), None)
    if not found:
        return None
    core, label, cats = found
    state['g_cat_text'] = ctx[-600:]
    asked = [stem(w) for w in words(ctx) if not w.isdigit() and not LICENSE_WORDS.match(w) and not GENERIC.fullmatch(w)]
    rows = db.execute(f"""SELECT family, vendor, min(name) AS name, count(*) AS n FROM products
        WHERE category IN ({','.join('?' * len(cats))}) AND available=1 AND price_kopecks>0 GROUP BY family""", cats).fetchall()
    person = bool(PERSON.search(ctx))

    def rank(r):
        name = normalize(r['name'])
        overlap = sum(1 for w in asked if len(w) >= 3 and w in name)
        odd = bool(ACCESSORY.search(name)) + bool(EDU.search(name)) + (bool(re.search(r'для\s+дома|домашн|home', name)) != person)
        return (odd, -bool(core.search(name)), -overlap, -r['n'])
    picked, vendors = [], set()
    for r in sorted(rows, key=rank):
        if r['vendor'] in vendors:
            continue
        offers = choose(_family(db, r['family']), state, text)
        if offers:
            picked.append(offers[0])
            vendors.add(r['vendor'])
        if len(picked) == 3:
            break
    if not picked:
        return None
    state['offered_ids'] = [o['id'] for o in picked]
    lines = [f'Для задачи «{label}» в каталоге есть, например:']
    lines += [f'— {price_line(o, state.get("quantity"))}' for o in picked]
    lines.append('Какой из вариантов посмотреть подробнее? Если нужен другой производитель, напишите его название.')
    return '\n'.join(lines), [('Выбрать: ' + o['name'][:45], 'select_offer', o['id']) for o in picked]


def faq_answer(text: str) -> str | None:
    found = faq_match(text)
    return found[0] if found else None


def faq_match(text: str):
    """(ответ, слова вокруг совпадения) — чтобы понять, не нашёлся ли «товар» по словам самого вопроса."""
    t = normalize(text)
    for pattern, answer in FAQ:
        m = pattern.search(t) if answer else None
        if m:
            return answer, t[max(0, m.start() - 30):m.end() + 30]
    return None


def is_closing(text: str) -> bool:
    t = normalize(text).strip()
    return len(t) <= 60 and '?' not in t and bool(CLOSING.match(t))


# ── один ход общего разговора ────────────────────────────────────────────────
def composition_reply(family: list[dict], offer_id: str | None, text: str) -> str:
    """Состав говорим только по карточке: что есть в названии или параметрах — подтверждаем, остального не придумываем."""
    item = next((o for o in family if o['id'] == offer_id), family[0])
    card = normalize(item['name'] + ' ' + ' '.join(f'{k} {v}' for k, v in item['parameters'].items()))
    asked = [w for w in re.findall(r'[a-z][a-z0-9+.\-]{1,}', normalize(text)) if w not in {'there', 'is', 'in'}]
    shown = ', '.join(w.capitalize() for w in asked) or 'нужные программы'
    link = f' Карточка: {item["url"]}' if item.get('url') else ''
    if asked and all(w in card for w in asked):
        return f'Да, по карточке «{item["name"]}»: {shown} указаны в составе.{link}'
    return (f'В карточке «{item["name"]}» состав пакета не расписан, поэтому про {shown} не буду гадать.{link} '
            'Точный состав подтвердит менеджер — нажмите «Позвать оператора».')


def catalog_turn(catalog: Path, state: dict, text: str, *, queue, quote, page_url: str = ''):
    page = re.search(r'store\.softline\.ru/.*?-(\d+)/?$', page_url or '')
    if page and not state.get('g_family') and catalog.is_file():
        with closing(read_only(catalog)) as db:
            row = db.execute('SELECT family FROM products WHERE id=?', (page.group(1),)).fetchone()
        if row:
            state['g_page_family'] = row['family']
    slug = re.search(r'store\.softline\.ru/(?:[^?#]*/)?([a-z0-9]+(?:-[a-z0-9]+)+)/?(?:[?#].*)?$', page_url or '')
    if slug and not page and not state.get('g_family') and not state.get('g_page_family') and catalog.is_file():
        parts = [w for w in slug.group(1).split('-') if not w.isdigit()]
        query = ' '.join(parts)
        with closing(read_only(catalog)) as db:
            fam, r, hit, _ = find_family(db, words(query), query)
        name = normalize(fam[0]['name']) if fam else ''
        if fam and r >= 0.9 and len(parts) >= 2 and all(w in name[:40] for w in words(query)):
            state['g_page_family'] = fam[0]['family']
    link = re.search(r'https?://store\.softline\.ru/\S*-(\d+)/?(?=[\s?#]|$)', text or '')
    link_only = bool(link) and not re.sub(r'https?://\S+', '', text or '').strip()
    if link and catalog.is_file() and not state.get('g_family'):
        with closing(read_only(catalog)) as db:
            row = db.execute('SELECT family FROM products WHERE id=?', (link.group(1),)).fetchone()
        if row:
            state['g_page_family'] = row['family']
    result = _catalog_turn(catalog, state, text, queue=queue, quote=quote)
    if result and link_only and '?' not in result[0]:
        result = (result[0].rstrip() + ' Сколько лицензий нужно — посчитать и подготовить КП?', result[1])
    if result and PRICE_OVERRIDE.search(normalize(text or '')):
        result = ('В КП ставлю только цену из каталога, другую цену назначить не могу; особые условия согласует менеджер.\n' + result[0], result[1])
    if CARD_FOR_ORG.search(normalize(text or '')):
        note = ('Если покупка для организации, счёт выставляется на организацию и оплачивается с её расчётного счёта — так документы '
                'подойдут бухгалтерии. Оплату личной картой за организацию лучше заранее согласовать с бухгалтерией; детали подскажет менеджер. ')
        result = ((result[0].rstrip() + '\n' if result else '') + note + queue('payment_question'), result[1] if result else [])
    if result and HANDOFF_ALWAYS.search(normalize(text or '')) and 'менеджер' not in result[0]:
        result = (result[0].rstrip() + '\nЗакупку по тендеру или 44/223-ФЗ оформляет менеджер. ' + queue('tender'), [])
    if result and result[0] == state.get('g_last') and result[0].rstrip().endswith('?'):
        if state.get('offered_ids'):
            result = ('Уточните, пожалуйста, какой вариант из списка выше подходит — или напишите количество и срок, пересчитаю.', result[1])
        else:
            result = ('Да, всё так, как написал выше. Подсказать что-то ещё по заказу?', [])
    if result:
        state['g_last'] = result[0]
    return result


def _catalog_turn(catalog: Path, state: dict, text: str, *, queue, quote):
    """Ответ по каталогу или None. queue(reason)->str ставит дело менеджеру; quote()->(reply, buttons) собирает КП."""
    if not text or not catalog.is_file():
        return None
    t = normalize(text)
    if is_closing(text):
        return 'Спасибо за обращение! Если появятся вопросы, пишите сюда — отвечу.', []
    provided_inn = re.search(r'\bинн\b[\s:=№]*\d', t)
    slots_from(text, state)
    tokens = words(text)
    if OFF_TOPIC.search(t):
        return 'Я помогаю с покупкой программ в Softline Store, с этим вопросом помочь не смогу. Если понадобится лицензия — напишите.', []
    if COMPLAINT.search(t):
        return 'Извините, что так получилось. Передаю ваш вопрос менеджеру целиком, он ответит здесь. ' + queue('complaint'), []
    status = REQUEST_STATUS.search(t)
    if status and not state.get('g_family'):
        num = re.search(r'(?:запрос|заявк|обращени)\w*\s+(?:на\s+кп\s+|кп\s+)?(?:№\s*)?(\d{4,})|№\s*(\d{4,})', t)
        number = f' № {num.group(1) or num.group(2)}' if num else ''
        return f'Статус запроса{number} проверит менеджер: у меня нет доступа к истории обращений. ' + queue('request_status'), []
    topic = support_topic(t)
    if topic:
        answer, reason = topic
        return (answer + queue(reason), []) if reason else (answer, [('Позвать оператора', 'handoff', '')])
    if HANDOFF_FIRST.search(t):
        return 'По вашему заказу проверит менеджер: у меня нет доступа к истории покупок. ' + queue('order_question'), []
    if (re.search(r'договор\w*.{0,25}пришлит|пришлит\w*.{0,25}договор|партн[её]рск\w*\s+услови', t)
            and not re.search(r'оферт', t)):
        return 'Договор и индивидуальные условия сотрудничества оформляет менеджер. ' + queue('needs_manager'), []
    if INSIST.search(t) and (state.get('g_family') or state.get('g_missing')):
        return 'Понял, нужен именно этот вариант. Его наличие и цену сверит менеджер. ' + queue('exact_product_request'), []

    with closing(read_only(catalog)) as db:
        if state.get('g_family') and COMPOSITION.search(t):
            current = _family(db, state['g_family'])
            if current:
                return composition_reply(current, state.get('offer_id'), text), [('Позвать оператора', 'handoff', '')]
        if state.get('g_items') and (provided_inn or state.get('awaiting_customer')):
            return quote()   # общий путь КП: проверка «уже у менеджера», недостающие реквизиты, черновик
        several = None if state.get('g_family') or SKU.search(normalize(text)) else multi_item(db, state, text, queue)
        if several:
            return several
        family, ratio, hit, unknown = find_family(db, tokens, text)
        if family and ratio < 0.5:
            family = []
        page_family = _family(db, state['g_page_family']) if state.get('g_page_family') and not state.get('g_family') else []
        same_vendor = page_family and family and family[0]['vendor'] == page_family[0]['vendor'] and 'pinned' not in hit
        if page_family and (not family or ratio < 0.95 or same_vendor):
            # клиент пишет со страницы товара: уточнение того же производителя — это про этот товар
            family, ratio, hit = page_family, 1.0, ['page']
        if state.get('g_family') and family and family[0]['family'] != state['g_family']:
            # уже говорим о товаре: уточнение ищем вместе с прежними словами, на новый товар переходим только по явному названию
            ctx = state.get('g_text', '') + ' ' + text
            refined, r2, hit2, _ = find_family(db, words(ctx), ctx)
            prev = set(state.get('g_query', '').split())
            fresh = {w for w in tokens if not w.isdigit()} - prev
            if refined and r2 >= 0.5 and prev & set(hit2) and fresh & set(hit2):
                family, hit = refined, hit2
            elif ratio < 0.95 or prev & set(hit) or EDITION_FOLLOWUP.fullmatch(t):
                family = []
        brand_set = {out for _, outs in ALIASES for out in outs.split() if not GENERIC.fullmatch(out) and not out.isdigit()}
        branded = bool(set(hit) & brand_set) or 'pinned' in hit
        named = branded or any(re.fullmatch(r'[a-z][a-z0-9.\-]{3,}', w) for w in hit)
        if hit == ['pinned'] and re.search(r'российск|отечествен|импортозамещ', t) and any(pt.search(t) for pt, _, _ in CATEGORIES):
            branded = named = False   # «отечественный офис» — не Microsoft Office
        if named and not branded and any(pt.search(t) for pt, _, _ in CATEGORIES):
            named = False   # «файловый антивирус для Ubuntu»: раздел назван, Ubuntu — не то, что покупают
        platform_only = not {w for w in hit if not w.isdigit()} - {'windows', 'linux', 'astra', 'alse', 'ubuntu', 'macos'}
        if not state.get('g_family') and (not named or platform_only) and ESIGN.search(t):
            # «подпись на токене из налоговой, для отчётности» — нужна лицензия КриптоПро CSP
            row = db.execute("SELECT family FROM products WHERE id='410137'").fetchone()
            if row:
                family, ratio, hit = _family(db, row['family']), 1.0, ['криптопро']
                named = True
        missing = [w for w in unknown if re.fullmatch(r'[a-z][a-z0-9.\-]{2,}', w)]
        if state.get('g_missing') and not state.get('g_family') and not named and not ANALOG_ASK.search(t) and not CHEAPER.search(t):
            # уточнение к товару, которого нет в каталоге: не ищем новый товар по словам «сетевая на 64 ip»
            return f'Запрос по «{state["g_missing"]}» уже у менеджера, уточнение он увидит в этом чате. Если нужен аналог из каталога, напишите «аналог».', []
        found = faq_match(fix_typos(db, text))
        info = found[0] if found else None
        spurious = bool(found) and (not family or ratio < 0.95 or all(stem(w)[:5] in found[1] for w in hit if not w.isdigit()))
        if not state.get('g_family') and not named and not page_family and (not missing or ANALOG_ASK.search(t)):
            browsed = category_reply(db, state, text)
            if browsed:
                return ((info + '\n') if info and info not in (state.get('g_last') or '') else '') + browsed[0], browsed[1]
        if info and spurious and not named and not state.get('g_family') and not page_family and not ESIGN.search(t):
            return info, []   # вопрос о порядке покупки, а не о товаре: слабое совпадение по словам вопроса не показываем
        named_new = bool(family) and family[0]['family'] != state.get('g_family')
        if named_new:
            state['g_family'] = family[0]['family']
            state['g_query'] = ' '.join(hit)
            state['g_text'] = (state.get('g_text', '') + ' ' + text) if state.get('g_family') else text
            state.pop('offer_id', None)
        elif state.get('g_family'):
            family = _family(db, state['g_family'])

        if (named_new and not state.get('g_edition') and re.search(r'\b(?:kaspersky|касперск\w*)\b', t)
                and state.get('quantity') and re.search(r'\b(?:компьютер|устройств|узл)', t)
                and re.search(r'\b[1-3]\s+и\s+[1-3]\s+год', digits(t))):
            return 'Для сравнения сроков уточните редакцию Kaspersky: стандартная или расширенная?', []

        special = state.get('flow') in ('cryptopro', 'mdaemon', 'needs', 'smolensk')
        if HANDOFF_ALWAYS.search(t) and not named_new:
            return 'Этот вопрос решает менеджер. ' + queue('needs_manager'), []
        if special and not named_new:
            answer = faq_answer(text)
            return (answer, []) if answer else None
        # клиент просит аналог или дешевле
        if ANALOG_ASK.search(t) or ANALOG_ASK.search(fix_typos(db, text)) or (CHEAPER.search(t) and state.get('g_family')):
            found = (None if CHEAPER.search(t) else category_reply(db, state, text)) or analog_reply(db, state, text, family)
            if found:
                return found
            missing = state.get('g_missing')
            return ((f'«{missing}» и близкого аналога в каталоге нет. ' if missing else 'Близкого аналога в каталоге не нашёл. ')
                    + 'Менеджер подберёт замену или поставку через партнёров Softline. ' + queue('analog_request')), []

    # товар назван, но в каталоге его нет
    if not state.get('g_family'):
        product_words = [w for w in unknown if re.fullmatch(r'[a-z][a-z0-9.\-]{2,}', w)]
        if product_words and not faq_answer(text):
            name = ' '.join('Р7-Офис' if w == 'r7office' else w for w in product_words[:3])
            state['g_missing'] = name
            state['g_cat_text'] = normalize(text)[-600:]   # «рассмотрим отечественный» дальше подбирается по разделу из первой реплики
            # кик-офф 26.11: товара нет в каталоге, но Softline может поставить его через менеджера — сразу передаём, КП сформирует менеджер
            return (f'«{name}» в каталоге Softline Store нет. Softline работает со многими производителями напрямую, поэтому передал запрос '
                    f'менеджеру: он проверит поставку и подготовит КП. ' + queue('not_in_catalog')
                    + ' Пока ждёте, могу подобрать похожее из каталога — напишите «аналог».'), [('Подобрать аналог', 'price', 'analog')]
        if state.get('g_missing') and INSIST.search(t):
            return 'Понял, нужен именно этот продукт. ' + queue('not_in_catalog'), []
        answer = faq_answer(text)
        if answer:
            return answer, []
        return None

    if state.get('g_missing') and INSIST.search(t):
        return 'Понял, нужен именно этот продукт. ' + queue('not_in_catalog'), []

    available = [o for o in family if o['available'] and o['price_kopecks']]
    if not available:
        title = family[0]['name'].split(',')[0] if family else 'Этот продукт'
        return (f'{title} есть в каталоге, но сейчас недоступен для заказа, поэтому цену не называю. '
                + queue('price_confirmation') + ' Если подойдёт замена, напишите «аналог» — предложу из каталога.'), []
    qty = state.get('quantity')
    tiered = [o for o in available if (o.get('sku') or '').upper().startswith(KASPERSKY_FAMILIES)]
    if qty and tiered and not any(units_for(o, qty) is not None for o in tiered):
        min_nodes = 10
        unit_word = 'устройство' if qty == 1 else 'устройств'
        tail = f': минимальный диапазон в каталоге — от {min_nodes} узлов. ' if qty < min_nodes else '. '
        return (f'У предложений Kaspersky для этого продукта нет подтверждённой цены на {qty} {unit_word}{tail}'
                + queue('price_confirmation')), []

    if (re.match(r'^(?:ооо|ао|пао|ип|гбу|мбу)\b', t) or re.search(r'сч[её]т на', t)) and not provided_inn:
        offers = choose(family, state, text)
        if offers:
            state['offer_id'] = offers[0]['id']
            state['offered_ids'] = [offers[0]['id']]
        return (f'Принял: {price_line(offers[0], state.get("quantity"))}. Для КП нужны ИНН и КПП организации (у ИП — только ИНН). Пришлёте?'
                if offers else 'Для КП нужны название, ИНН и КПП организации. Пришлёте?'), []
    # реквизиты — сразу к КП
    if provided_inn:
        offers = choose(family, state, text)
        if len(offers) == 1 or (offers and state.get('offer_id') in {o['id'] for o in offers}):
            state['offer_id'] = state.get('offer_id') if state.get('offer_id') in {o['id'] for o in offers} else offers[0]['id']
            state.setdefault('quantity', 1)
            return quote()
        if offers:
            state['offer_id'] = offers[0]['id']
            state.setdefault('quantity', 1)
            return quote()
        return 'Позицию для КП уточнит менеджер. ' + queue('quote_review'), []

    answer = faq_answer(text)
    compared = compare_terms(family, state, text)
    if compared:
        return compared
    offers = choose(family, state, text)
    discount = 5 if re.search(r'скидк\w*\s*5\s*%|5\s*%\s*скидк', t) else 0
    if len(offers) == 1:
        offer = offers[0]
        state['offer_id'] = offer['id']
        state['offered_ids'] = [offer['id']]
        qty = state.get('quantity')
        line = price_line(offer, qty, discount)
        tail = ' Для КП пришлите название организации, ИНН и КПП.' if not discount else ''
        return (answer + '\n' if answer else '') + line + '.' + tail, [('Подготовить КП', 'quote', '')]
    shown = offers[:4]
    if state.get('offered_ids') == [o['id'] for o in shown] or (shown and shown[0]['id'] in FLAGSHIP):
        offer = shown[0]   # уже показывали этот список — даём лучший вариант с ценой
        state['offer_id'] = offer['id']
        state['offered_ids'] = [offer['id']]
        return ((answer + '\n') if answer else '') + price_line(offer, state.get('quantity'), discount) + '. Для КП пришлите название организации, ИНН и КПП.', [('Подготовить КП', 'quote', '')]
    state['offered_ids'] = [o['id'] for o in shown]
    question = _clarify_question(shown, state)
    lines = [(answer + '\n') if answer else '', 'Нашёл в каталоге:']
    lines += [f'— {price_line(o, state.get("quantity"))}' for o in shown]
    lines.append(question)
    return '\n'.join(x for x in lines if x), [('Выбрать: ' + o['name'][:45], 'select_offer', o['id']) for o in shown]


ITEM_SPLIT = re.compile(r'\s+(?:и|плюс|а\s+также|ещё|еще)\s+(?=[1-9]\d{0,3}\s+(?!год\b|год[а-я]+|лет\b|мес))'
                        r'|;|\n|\s\+\s(?=[1-9]\d{0,3}\s)')


COMMA_ITEM = re.compile(r',\s*')
QTY_WORDS = re.compile(r'\b[1-9]\d{0,3}\s*(?:шт\w*|лиценз\w*|рабоч\w*\s+мест\w*|мест\w*|пользовател\w*|узл\w*|устройств\w*)\.?(?!\w)', re.I)
LEADING_QTY = re.compile(r'^\s*(?:беру\s+|нуж\w*\s+|ещё\s+|еще\s+)?([1-9]\d{0,3})\s+(?!(?:год|года|лет|мес|месяц\w*)\b)(?=[^\d\s])', re.I)


def item_quantity(part: str) -> int | None:
    """«2 Office …» — число перед названием тоже количество (кроме «2 года», «12 месяцев»)."""
    m = LEADING_QTY.match(part)
    return int(m.group(1)) if m else quantity(part)


def multi_item(db, state: dict, text: str, queue=None):
    """Несколько товаров в одной реплике: по строке на позицию и общий итог. Суммы — только цена каталога × количество.
    Позицию, которую не нашли, не теряем молча: называем её клиенту."""
    plain = digits(text)
    parts = [p for p in ITEM_SPLIT.split(plain) if p and p.strip()]
    if len(parts) < 2:   # «Windows 11 Pro 1 шт, Office … 2 шт» — через запятую, только если у каждой части своё количество
        commas = [p for p in COMMA_ITEM.split(plain) if p.strip()]
        if len(commas) >= 2 and all(item_quantity(p) for p in commas):
            parts = commas
    if len(parts) < 2:
        return None
    items, seen, missed = [], set(), []
    for part in parts:
        fam, conf, _, _ = find_family(db, words(part), part)
        lead = LEADING_QTY.match(part)
        if (not fam or conf < 0.9) and (QTY_WORDS.search(part) or (lead and re.match(r'[a-z]', part[lead.end():], re.I))):
            # «Kaspersky Password Manager 3 шт», «2 Office …»: количество мешает узнать товар — пробуем без него
            name = QTY_WORDS.sub(' ', LEADING_QTY.sub(' ', part, count=1))
            fam, conf, _, _ = find_family(db, words(name), name)
        if not fam or conf < 0.9 or fam[0]['family'] in seen:
            if item_quantity(part) and (not fam or fam[0]['family'] not in seen):
                missed.append(' '.join(part.split())[:60])
            continue
        qty = item_quantity(part) or 1
        offers = choose(fam, {'g_term': term(part), 'quantity': qty}, part)
        if not offers:
            return None  # одну из позиций не нашли с ценой — не считаем итог наполовину
        seen.add(fam[0]['family'])
        units = units_for(offers[0], qty)
        family_sku = next((f for f in KASPERSKY_FAMILIES if (offers[0].get('sku') or '').upper().startswith(f)), None)
        if family_sku:   # у Касперского цена зависит от диапазона узлов: берём позицию своего диапазона или сверку у менеджера
            tiered = tiered_annual_offer(db, family_sku, qty)
            offers, units = ([tiered], qty) if tiered else (offers, None)
        if units is None:  # позиция не рассчитана на такое количество — итог не считаем, сверит менеджер
            return (f'Для «{offers[0]["name"]}» на {qty} нужно подобрать другую позицию по количеству — сверит менеджер. '
                    + queue('price_confirmation'), [])
        items.append((offers[0], qty, units))
    if len(items) < 2 and not (items and missed):
        return None
    state['g_items'] = [{'id': o['id'], 'quantity': q, 'units': u} for o, q, u in items]
    state['offered_ids'] = [o['id'] for o, _, _ in items]
    lines = ['Посчитал по позициям:'] + [f'{i}. {price_line(o, q, units=u)}' for i, (o, q, u) in enumerate(items, 1)]
    lines.append(f'Итого: {money(sum(o["price_kopecks"] * u for o, _, u in items))}.')
    if missed:
        lines.append('Не смог точно определить: ' + '; '.join(f'«{m}»' for m in missed) + ' — напишите эту позицию отдельным сообщением, добавлю.')
    lines.append('Для КП пришлите название организации, ИНН и КПП.')
    return '\n'.join(lines), [('Подготовить КП', 'quote', '')]


def multi_quote(db, state: dict, queue):
    """Реквизиты пришли после расчёта нескольких позиций: черновик КП с теми же строками — менеджеру."""
    if not state.get('inn') and state.get('inn_rejected'):
        return (f'ИНН {state["inn_rejected"]} не проходит проверку контрольной цифры. Проверьте, пожалуйста, нет ли опечатки? '
                'Если ИНН верный, пришлите его ещё раз — передам менеджеру на проверку.'), []
    need = [label for key, label in (('customer', 'название организации'), ('inn', 'ИНН')) if not state.get(key)]
    if not state.get('kpp') and len(state.get('inn') or '') != 12:
        need.append('КПП')
    if need:
        state['awaiting_customer'] = True
        return f'Для КП укажите ещё {", ".join(need)}.', []
    lines, total, items = [f'Черновик КП для {state["customer"]}:'], 0, []
    meta = db.execute("SELECT value FROM metadata WHERE name='source_date'").fetchone()
    source_date = meta[0] if meta else ''
    for i, item in enumerate(state['g_items'], 1):
        found = db.execute('SELECT * FROM products WHERE id=?', (item['id'],)).fetchone()
        offer = view(found) if found else None
        units = (item.get('units') or units_for(offer, item['quantity'])) if offer and offer['available'] and offer['price_kopecks'] else None
        if units is None:   # позиция пропала из каталога после обновления или не покрывает количество — не печатаем КП наполовину
            state.pop('g_items', None)
            state['awaiting_customer'] = False
            name = f'«{offer["name"]}»' if offer else 'Одна из позиций'
            return f'{name} нужно пересчитать: в каталоге изменились цена или наличие. ' + queue('price_confirmation'), []
        total += offer['price_kopecks'] * units
        items.append({'id': offer['id'], 'sku': offer.get('sku') or '', 'name': offer['name'], 'price_kopecks': offer['price_kopecks'],
                      'quantity': units, 'requested': item['quantity']})
        lines.append(f'{i}. {price_line(offer, item["quantity"], units=units)}')
    percent = 0
    try:
        percent = int(float(str(state.get('coupon_percent') or 0).replace(',', '.')))
    except ValueError:
        pass
    percent = percent if 0 < percent <= 5 else 0
    after = f', со скидкой по купону {percent}% — {money(discounted(total, percent))}' if percent else ''
    # КП на несколько позиций — тот же путь, что и на одну: менеджер одобряет — клиент получает PDF
    state['quote'] = {
        'offer': {'id': items[0]['id'], 'sku': '', 'name': f'КП на {len(items)} поз.: ' + '; '.join(x['name'][:40] for x in items),
                  'price_kopecks': total, 'source_date': source_date},
        'items': items, 'quantity': 1, 'requested_users': sum(x['requested'] for x in items),
        'customer': state['customer'], 'inn': state['inn'], 'kpp': state.get('kpp') or '',
        'amount_kopecks': total, 'vat_kopecks': None, 'vat_status': 'НДС уточняется менеджером', 'payment_terms': 'Предоплата по оферте',
        'source_date': source_date,
    }
    if percent:
        state['quote'].update(discount_percent=percent, amount_after_discount_kopecks=discounted(total, percent))
    state['awaiting_customer'] = False
    lines.append(f'Итого: {money(total)}{after}. Сумма по каталогу проверена. ' + queue('quote_review'))
    state.pop('g_items', None)
    return '\n'.join(lines), []


TERM_LABEL = {0: 'бессрочно', 1: '1 месяц', 12: '1 год', 24: '2 года', 36: '3 года'}


def compare_terms(family: list[dict], state: dict, text: str):
    """«Сравните на один год и на три года» — по позиции на каждый названный срок и разница в цене."""
    asked = list(dict.fromkeys(m for m, p in TERM if p.search(digits(text))))
    if len(asked) < 2 or not family:
        return None
    rows = []
    for months in asked:
        found = choose(family, dict(state, g_term=months), text)
        if found and offer_term(found[0]) == months:
            rows.append((months, found[0]))
    if len(rows) < 2:
        return None
    rows.sort(key=lambda x: (x[0] == 0, x[0]))
    qty = state.get('quantity')
    lines = ['Сравнение по сроку:'] + [f'— {TERM_LABEL.get(m, f"{m} мес.")}: {price_line(o, qty)}' for m, o in rows]
    (m1, a), (m2, b) = rows[0], rows[1]
    if m1 and m2 and a['price_kopecks'] and b['price_kopecks']:
        per_year = lambda o, m: o['price_kopecks'] * 12 / m  # noqa: E731
        cheap, dear = sorted([(per_year(a, m1), m1), (per_year(b, m2), m2)])
        if dear[0] > cheap[0]:  # проценты, а не рубли: в ответе только суммы, которые есть в каталоге
            lines.append(f'В пересчёте на год вариант «{TERM_LABEL.get(cheap[1])}» дешевле на {round((1 - cheap[0] / dear[0]) * 100)} %.')
    state['offered_ids'] = [o['id'] for _, o in rows]
    lines.append('Какой срок оформить?')
    return '\n'.join(lines), [('Выбрать: ' + TERM_LABEL.get(m, str(m)), 'select_offer', o['id']) for m, o in rows]


def _looks_like_product(tokens: list[str], text: str) -> bool:
    t = normalize(text)
    if re.search(r'[a-z]{3,}', t) and any(re.fullmatch(r'[a-z][a-z0-9.\-]{2,}', w) for w in tokens):
        return True
    return bool(re.search(r'(?:лицензи\w*|подписк\w*|купить|приобрести|стоимость)\s+(?:на\s+)?[«"]?[a-zа-я]', t)) and len(tokens) <= 5


def _clarify_question(shown: list[dict], state: dict) -> str:
    terms = {offer_term(o) for o in shown}
    if state.get('g_term') is None and len(terms) > 1:
        return 'На какой срок нужна лицензия?'
    if not state.get('quantity'):
        return 'Сколько лицензий нужно?'
    return 'Какой вариант подходит?'


def analog_reply(db, state: dict, text: str, family: list[dict]):
    t = aliased(text + ' ' + (state.get('g_missing') or '') + ' ' + state.get('g_query', ''))
    if CHEAPER.search(normalize(text)) and family:
        offers = sorted([o for o in family if o['available'] and o['price_kopecks']], key=lambda o: o['price_kopecks'])[:3]
        if offers:
            state['offered_ids'] = [o['id'] for o in offers]
            return ('Самые доступные варианты в каталоге:\n' + '\n'.join('— ' + price_line(o, state.get('quantity')) for o in offers)
                    + '\nКакой вариант подходит?'), [('Выбрать: ' + o['name'][:45], 'select_offer', o['id']) for o in offers]
    query = next((q for p, q in ANALOG_SEARCH if re.search(p, t)), None)
    if ('отечеств' in normalize(text) or 'российск' in normalize(text)) and re.search(r'server|windows', t) and not query:
        query = 'astra linux'
    rows = []
    if query:
        rows = [view(r) for r in db.execute('''
            SELECT p.* FROM product_search JOIN products p ON p.rowid=product_search.rowid
            WHERE product_search MATCH ? AND p.available=1 AND p.price_kopecks IS NOT NULL
            ORDER BY bm25(product_search, 10.0, 6.0, 1.0, 0.1) LIMIT 3''', (_match_tokens(query.split()).replace(' OR ', ' AND '),)).fetchall()]
    if not rows:
        return None   # аналога в каталоге нет — решит вызывающий: раздел каталога или менеджер
    state['offered_ids'] = [o['id'] for o in rows]
    missing = state.get('g_missing') or ''
    head = f'«{missing}» нет в каталоге. ' if missing else 'Точно такого товара нет в каталоге. '
    return (head + 'Аналоги, которые есть в каталоге:\n' + '\n'.join('— ' + price_line(o, state.get('quantity')) for o in rows)
            + '\nКакой вариант рассмотреть?'), [('Выбрать: ' + o['name'][:45], 'select_offer', o['id']) for o in rows]
