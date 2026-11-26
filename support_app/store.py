import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = '''
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    client_hash TEXT NOT NULL UNIQUE,
    offer TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','pending','approved','rejected')),
    version INTEGER NOT NULL DEFAULT 0,
    decision_key TEXT,
    decision_choice TEXT,
    decision_note TEXT NOT NULL DEFAULT '',
    payment_due TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    event TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL CHECK (kind IN ('quote','invoice')),
    offer TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    case_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_state (
    case_id TEXT PRIMARY KEY REFERENCES cases(id),
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    role TEXT NOT NULL CHECK (role IN ('client','agent','manager')),
    text TEXT NOT NULL,
    document_url TEXT,
    buttons TEXT NOT NULL DEFAULT '[]',
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS chat_messages_case ON chat_messages (case_id,id);
CREATE TABLE IF NOT EXISTS rules (
    customer TEXT NOT NULL,
    contract_ref TEXT NOT NULL,
    days INTEGER NOT NULL,
    max_kopecks INTEGER NOT NULL,
    guidance TEXT NOT NULL,
    source_case TEXT NOT NULL REFERENCES cases(id),
    PRIMARY KEY (customer, contract_ref)
);
CREATE TABLE IF NOT EXISTS model_usage (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    day TEXT NOT NULL,
    cost_microrubles INTEGER NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER
);
CREATE TABLE IF NOT EXISTS mail_outbox (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL CHECK (kind IN ('handoff','approved')),
    offer TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at INTEGER NOT NULL DEFAULT 0,
    sent_at INTEGER,
    UNIQUE(case_id, kind)
);
'''


class Store:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.execute('PRAGMA journal_mode = WAL')
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def reserve_model(self, case_id: str, day: str, ceiling: int, daily: int, total: int) -> int | None:
        with self.connect(write=True) as db:
            budget = db.execute('''
                SELECT COALESCE(SUM(cost_microrubles),0) AS total,
                       COALESCE(SUM(CASE WHEN day=? THEN cost_microrubles ELSE 0 END),0) AS today
                FROM model_usage
            ''', (day,)).fetchone()
            if budget['today'] + ceiling > daily or budget['total'] + ceiling > total:
                append_event(db, case_id, 'model_budget_exceeded')
                return None
            cur = db.execute('INSERT INTO model_usage(case_id,day,cost_microrubles) VALUES (?,?,?)', (case_id, day, ceiling))
            return cur.lastrowid

    def record_model(self, reservation: int, input_tokens: int, output_tokens: int, cost: int):
        with self.connect(write=True) as db:
            db.execute('''
                UPDATE model_usage SET input_tokens=?, output_tokens=?, cost_microrubles=? WHERE id=?
            ''', (input_tokens, output_tokens, cost, reservation))


def append_event(db: sqlite3.Connection, case_id: str, event: str, detail: str = ''):
    db.execute('INSERT INTO journal(case_id,event,detail) VALUES (?,?,?)', (case_id, event, detail))


def chat_state(db, case_id: str) -> dict:
    row = db.execute('SELECT data FROM chat_state WHERE case_id=?', (case_id,)).fetchone()
    return json.loads(row['data']) if row else {}


def save_chat_state(db, case_id: str, state: dict):
    db.execute('''INSERT INTO chat_state(case_id,data) VALUES (?,?)
                  ON CONFLICT(case_id) DO UPDATE SET data=excluded.data''', (case_id, json.dumps(state, ensure_ascii=False)))


def save_chat_message(db, case_id: str, role: str, text: str, *, document_url=None, buttons=()):
    cur = db.execute('INSERT INTO chat_messages(case_id,role,text,document_url,buttons) VALUES(?,?,?,?,?)',
                     (case_id, role, text, document_url, json.dumps(buttons, ensure_ascii=False)))
    row = db.execute('SELECT id,role,text,document_url,buttons,created FROM chat_messages WHERE id=?', (cur.lastrowid,)).fetchone()
    return {**dict(row), 'buttons': json.loads(row['buttons'])}


def read_chat_messages(db, case_id: str, after: int | None = None):
    if after is None:
        rows = reversed(db.execute('''SELECT id,role,text,document_url,buttons,created FROM chat_messages
                                      WHERE case_id=? ORDER BY id DESC LIMIT 200''', (case_id,)).fetchall())
    else:
        rows = db.execute('''SELECT id,role,text,document_url,buttons,created FROM chat_messages
                             WHERE case_id=? AND id>? ORDER BY id LIMIT 200''', (case_id, after)).fetchall()
    return [{**dict(row), 'buttons': json.loads(row['buttons'])} for row in rows]


def queue_mail(db: sqlite3.Connection, case_id: str, kind: str, offer: dict):
    db.execute('''
        INSERT INTO mail_outbox(id,case_id,kind,offer) VALUES (?,?,?,?)
        ON CONFLICT(case_id,kind) DO NOTHING
    ''', (f'{case_id}-{kind}', case_id, kind, json.dumps(offer)))


def case_view(case: sqlite3.Row) -> dict:
    return {
        'id': case['id'],
        'state': case['state'],
        'version': case['version'],
        'offer': json.loads(case['offer']),
        'payment_due': case['payment_due'],
        'decision_note': case['decision_note'],
    }
