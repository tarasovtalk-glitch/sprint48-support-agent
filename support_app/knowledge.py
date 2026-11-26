"""База ответов менеджера: менеджер отметил ответ «запомнить» — следующий клиент с тем же вопросом получает его сразу.

Вопрос и ответ обезличиваются до записи (почта, телефон, ИНН/КПП, номера, название организации).
Совпадение — по основам смысловых слов вопроса: не меньше двух общих и доля общих (Жаккар) от 0,6.
"""
import re

from .catalog import normalize
from .dialog import stem, words

SCHEMA = '''
CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    keys TEXT NOT NULL,
    source_case TEXT NOT NULL REFERENCES cases(id),
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''

# слова просьбы позвать человека не описывают сам вопрос
HANDOFF_WORDS = re.compile(r'^(?:позов|позвать|позвон|подключ|соедин|менеджер|оператор|специалист|человек|живой|ответьт|напишит|свяжит)')
MASKS = [
    (re.compile(r'\S+@\S+\.\w+'), '[почта]'),
    (re.compile(r'(?:\+7|\b8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b'), '[тел]'),
    (re.compile(r'\b(?:инн|кпп|огрн\w*|бик|р/?с|к/?с)\b[\s:=№]*\d+', re.I), '[реквизит]'),
    (re.compile(r'\b\d{9,}\b'), '[номер]'),
    (re.compile(r'\b(?:ооо|оао|пао|зао|ао|ип|гбу|мбу|фгуп|нко)\s*(?:[«"][^»"]{1,60}[»"]|[А-ЯЁ][\w\-]+(?:\s+[А-ЯЁ][\w\-]+){0,2})', re.I),
     '[организация]'),
]
MIN_COMMON = 2
MIN_JACCARD = 0.6


def mask(text: str) -> str:
    out = text or ''
    for pattern, repl in MASKS:
        out = pattern.sub(repl, out)
    return re.sub(r'\s+', ' ', out).strip()


def keys(text: str) -> set[str]:
    out = set()
    for w in words(text or ''):
        if w.isdigit() or len(w) < 4 or HANDOFF_WORDS.match(w):
            continue
        out.add(stem(w)[:6])
    return out


def ensure(db):
    db.executescript(SCHEMA)


def save_answer(db, case_id: str, question: str, answer: str) -> dict:
    question, answer = mask(question), mask(answer)
    found = sorted(keys(question))
    if len(found) < MIN_COMMON:
        raise ValueError('В вопросе слишком мало смысловых слов, чтобы узнать его в следующий раз.')
    if not answer:
        raise ValueError('Пустой ответ не сохраняется.')
    ensure(db)
    cur = db.execute('INSERT INTO knowledge(question,answer,keys,source_case) VALUES (?,?,?,?)',
                     (question, answer, ' '.join(found), case_id))
    return {'id': cur.lastrowid, 'question': question, 'answer': answer, 'keys': found, 'source_case': case_id}


def find_answer(db, text: str) -> dict | None:
    asked = keys(text)
    if len(asked) < MIN_COMMON:
        return None
    ensure(db)
    best, best_score = None, 0.0
    for row in db.execute('SELECT id,question,answer,keys FROM knowledge ORDER BY id DESC LIMIT 500'):
        saved = set(row['keys'].split())
        common = asked & saved
        score = len(common) / len(asked | saved)
        exact = normalize(mask(text)) == normalize(row['question'])
        if exact or (len(common) >= MIN_COMMON and score >= MIN_JACCARD and score > best_score):
            best, best_score = dict(row), (1.0 if exact else score)
            if exact:
                break
    return best


def question_for(messages: list[dict]) -> str:
    """Вопрос клиента для записи: последняя реплика клиента с вопросом по сути (не «позовите менеджера»)."""
    for m in reversed(messages):
        if m['role'] == 'client' and len(keys(m['text'])) >= MIN_COMMON:
            return m['text']
    return ''


def all_answers(db, limit=50) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.execute('SELECT id,question,answer,source_case,created FROM knowledge ORDER BY id DESC LIMIT ?', (limit,))]
