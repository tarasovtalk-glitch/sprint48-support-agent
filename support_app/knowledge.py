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
    (re.compile(r'(?:№\s*)?\b\d{6,}\b'), '[номер]'),
    (re.compile(r'\b(?:ооо|оао|пао|зао|ао|ип|гбу|мбу|фгуп|нко)\s*(?:[«"][^»"]{1,60}[»"]|[А-ЯЁ][\w\-]+(?:\s+[А-ЯЁ][\w\-]+){0,2})', re.I),
     '[организация]'),
    (re.compile(r'(?:\b(?:г|гор|ул|пр|просп|пер|наб|ш|д|корп|стр|кв|оф)\.\s*|\b(?:улица|проспект|переулок|набережная|шоссе|дом|квартира|офис)\s+)'
                r'[\wЁё\-]+(?:[ \t]+\d+\w?)?', re.I), '[адрес]'),
    (re.compile(r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна|чна|ична|инична)\b'), '[имя]'),
    (re.compile(r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.)?|\b[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.\s*)?[А-ЯЁ][а-яё]+'), '[имя]'),
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


def has_private(text: str) -> bool:
    """В тексте есть данные конкретного клиента — такой ответ нельзя показывать другим."""
    return mask(text) != re.sub(r'\s+', ' ', text or '').strip()


def keys(text: str) -> set[str]:
    out = set()
    for w in words(text or ''):
        if w.isdigit() or len(w) < 4 or HANDOFF_WORDS.match(w) or FILLER_WORDS.match(w):
            continue
        out.add(stem(w)[:6])
    return out


def numbers(text: str) -> set[str]:
    return set(re.findall(r'\d+', digits(text or '')))


def negated(text: str) -> bool:
    return bool(NEGATION.search(normalize(text or '')))


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
