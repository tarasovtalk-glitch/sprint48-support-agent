import hashlib
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import AliasChoices, BaseModel, Field, StrictBool, model_validator

from .chat import buttons, customer_text, intent_cues, run_turn, tool_request
from .documents import render_catalog_quote, render_pdf, rubles
from .mail import run_mail_queue
from .model import choose_tool, classify
from .scenario import load_scenario
from .selection import catalog_router
from .store import (
    Store, append_event, case_view, chat_state, queue_mail,
    read_chat_messages, save_chat_message, save_chat_state,
)


PREFIX = '/support/api'
DOCUMENT_TTL = 15 * 60
DEMO_SOURCE = Path(__file__).with_name('demo.json')


class Message(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    action: Literal['price', 'quote', 'invoice', 'deferral', 'placement', 'focus', 'term',
                    'deployment', 'select_offer', 'handoff', 'more_discount'] | None = None
    value: str = Field(default='', max_length=32)
    page_url: str = Field(default='', max_length=600)
    channel: Literal['chat', 'email', 'call_demo'] = 'chat'

    @model_validator(mode='after')
    def one_input(self):
        if (self.text is None) == (self.action is None):
            raise ValueError('Provide exactly one of text or action.')
        if self.text is not None and not self.text.strip():
            raise ValueError('Enter a message.')
        if self.text is not None and len(self.text.encode('utf-8')) > 2500:
            raise ValueError('Message is too long.')
        return self


class Decision(BaseModel):
    choice: Literal['approve', 'reject']
    version: int = Field(ge=0)
    request_id: UUID
    note: str = Field(default='', max_length=400, validation_alias=AliasChoices('reply', 'note'))


class RuleConfirmation(BaseModel):
    confirmed: StrictBool


def require_key(expected: str, supplied: str):
    if len(expected) < 24:
        raise HTTPException(503, 'Demo access is not configured.')
    if not secrets.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(401, 'Access key required.')


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_case(db, case_id: str):
    row = db.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Case not found.')
    return row


def due_date(offer: dict) -> str:
    return (date.fromisoformat(offer['as_of']) + timedelta(days=offer['requested_days'])).isoformat()


def create_app(database: Path, scenario_path: Path = DEMO_SOURCE) -> FastAPI:
    scenario = load_scenario(scenario_path)
    store = Store(database)
    demo_key = os.environ.get('SUPPORT_DEMO_KEY', '')
    manager_key = os.environ.get('SUPPORT_MANAGER_KEY', '')
    model_key = os.environ.get('YANDEX_API_KEY', '')
    model_uri = os.environ.get('YANDEX_MODEL_URI', '')
    daily_limit = int(os.environ.get('SUPPORT_DAILY_BUDGET_RUB', '50')) * 1_000_000
    total_limit = int(os.environ.get('SUPPORT_TOTAL_BUDGET_RUB', '250')) * 1_000_000
    font_default = 'C:/Windows/Fonts/arial.ttf' if os.name == 'nt' else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font_path = Path(os.environ.get('SUPPORT_PDF_FONT', font_default))
    if not font_path.is_file():
        raise ValueError('SUPPORT_PDF_FONT must point to a TrueType font.')
    chat_only = os.environ.get('SUPPORT_CHAT_ONLY', '1') == '1'
    smtp_host = '' if chat_only else os.environ.get('SUPPORT_SMTP_HOST', '')
    smtp_port = int(os.environ.get('SUPPORT_SMTP_PORT', '1025'))

    @asynccontextmanager
    async def lifespan(_app):
        if smtp_host:
            stop = Event()
            worker = Thread(target=run_mail_queue, args=(store, smtp_host, smtp_port, font_path, stop), daemon=True)
            worker.start()
        try:
            yield
        finally:
            if smtp_host:
                stop.set()
                worker.join(timeout=6)

    app = FastAPI(title='SMF Support', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    catalog_path = Path(os.environ.get('SUPPORT_CATALOG_DATABASE', database.with_name('catalog.sqlite3')))
    app.include_router(catalog_router(catalog_path, demo_key, font_path, require_key), prefix=PREFIX)

    def manager(x_manager_key: str = Header(default='')):
        require_key(manager_key, x_manager_key)

    def client(authorization: str = Header(default='')) -> str:
        prefix, _, token = authorization.partition(' ')
        if prefix.lower() != 'bearer' or not 30 <= len(token) <= 64:
            raise HTTPException(401, 'Session token required.')
        with store.connect() as db:
            row = db.execute('SELECT id FROM cases WHERE client_hash=?', (token_hash(token),)).fetchone()
        if row is None:
            raise HTTPException(401, 'Session token required.')
        return row['id']

    @app.get(PREFIX + '/health', status_code=204)
    def health():
        with store.connect() as db:
            db.execute('SELECT 1')
        return Response(status_code=204)

    @app.post(PREFIX + '/sessions', status_code=201)
    def session(x_demo_key: str = Header(default='')):
        require_key(demo_key, x_demo_key)
        session_token = secrets.token_urlsafe(32)
        case_id = uuid4().hex
        with store.connect(write=True) as db:
            db.execute('INSERT INTO cases(id,client_hash,offer) VALUES(?,?,?)', (case_id, token_hash(session_token), json.dumps(scenario.offer())))
            append_event(db, case_id, 'opened', scenario.source)
            view = case_view(get_case(db, case_id))
        return {'session_token': session_token, 'case': view}

    @app.get(PREFIX + '/case')
    def my_case(case_id: str = Depends(client)):
        with store.connect() as db:
            return case_view(get_case(db, case_id))

    @app.get(PREFIX + '/case/messages')
    def client_messages(after: int | None = Query(default=None, ge=0), case_id: str = Depends(client)):
        with store.connect() as db:
            return {'messages': read_chat_messages(db, case_id, after)}

    @app.post(PREFIX + '/case/messages')
    def message(payload: Message, case_id: str = Depends(client)):
        if chat_only:
            if payload.channel != 'chat':
                raise HTTPException(422, 'This stand accepts chat messages only.')
            with store.connect() as db:
                existing_context = chat_state(db, case_id)
            plan = tool_request(payload.text or '', payload.action, payload.value, existing_context)
            model_options = {'api_key': model_key, 'model_uri': model_uri, 'daily': daily_limit, 'total': total_limit}
            selected_tool = choose_tool(store, case_id, *plan, **model_options) if plan else None
            cues = intent_cues(payload.text) if payload.text and not existing_context else ''
            hint = classify(store, case_id, cues, **model_options) if cues and not plan else 'unknown'
            with store.connect(write=True) as db:
                state = chat_state(db, case_id)
                if selected_tool:
                    append_event(db, case_id, 'model_tool_selected', selected_tool)
                client_entry = save_chat_message(db, case_id, 'client', customer_text(payload.text, payload.action, payload.value))
                reply, choices = run_turn(db, get_case(db, case_id), state, catalog_path,
                                          text=payload.text or '', action=payload.action, value=payload.value, intent_hint=hint,
                                          page_url=payload.page_url, tool=selected_tool)
                save_chat_state(db, case_id, state)
                reply_buttons = buttons(choices)
                agent_entry = save_chat_message(db, case_id, 'agent', reply, buttons=reply_buttons)
                return {'reply': reply, 'intent': 'chat', 'document_url': None, 'buttons': reply_buttons,
                        'case': case_view(get_case(db, case_id)), 'messages': [client_entry, agent_entry]}
        intent = payload.action or classify(store, case_id, payload.text, api_key=model_key, model_uri=model_uri, daily=daily_limit, total=total_limit)
        document_url = None
        with store.connect(write=True) as db:
            row = get_case(db, case_id)
            offer = json.loads(row['offer'])
            amount = rubles(offer['renewal_total_kopecks'])
            append_event(db, case_id, 'received', f'{payload.channel}:{intent}')
            if intent == 'price':
                append_event(db, case_id, 'price_calculated', offer['source'])
                reply = f'По заказу {offer["previous_order"]} на {offer["quantity"]} узлов продление стоит {amount} Новые лицензии стоят {rubles(offer["new_total_kopecks"])}'
            elif intent in {'quote', 'invoice'}:
                access_id = secrets.token_urlsafe(32)
                offer['payment_due'] = row['payment_due']
                db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)', (token_hash(access_id), case_id, intent, json.dumps(offer), int(time.time()) + DOCUMENT_TTL, row['version']))
                document_url = f'{PREFIX}/documents/{access_id}'
                append_event(db, case_id, 'document_prepared', intent)
                reply = f'Подготовил {"коммерческое предложение" if intent == "quote" else "черновик счёта"} на {amount}'
            elif intent == 'deferral':
                if row['state'] == 'open':
                    valid_rule = db.execute('''
                        SELECT 1 FROM rules WHERE customer=? AND contract_ref=? AND days=? AND max_kopecks>=?
                    ''', (offer['customer'], offer['contract_ref'], offer['requested_days'], offer['renewal_total_kopecks'])).fetchone()
                    if valid_rule:
                        offer['payment_due'] = due_date(offer)
                        db.execute("UPDATE cases SET state='approved', version=version+1, payment_due=? WHERE id=?", (offer['payment_due'], case_id))
                        append_event(db, case_id, 'rule_applied')
                        if smtp_host:
                            queue_mail(db, case_id, 'approved', offer)
                    else:
                        db.execute("UPDATE cases SET state='pending', version=version+1 WHERE id=?", (case_id,))
                        append_event(db, case_id, 'sent_to_manager')
                        if smtp_host:
                            queue_mail(db, case_id, 'handoff', offer)
                final = get_case(db, case_id)
                reply = {
                    'pending': 'Передал запрос об отсрочке менеджеру. Решение появится в этом обращении.',
                    'approved': f'Отсрочка согласована. Оплатить до {final["payment_due"]}.',
                    'rejected': 'Менеджер отказал в отсрочке.',
                }[final['state']]
            else:
                reply = 'Уточните, пожалуйста: нужна цена, КП, счёт или отсрочка?'
            if payload.channel != 'chat':
                append_event(db, case_id, 'channel_result', f'{payload.channel}: {reply}')
            view = case_view(get_case(db, case_id))
        return {'reply': reply, 'intent': intent, 'document_url': document_url, 'case': view}

    @app.get(PREFIX + '/documents/{access_id}')
    def document(access_id: str):
        if not 30 <= len(access_id) <= 64:
            raise HTTPException(404, 'Document not found.')
        with store.connect() as db:
            row = db.execute('''
                SELECT documents.* FROM documents JOIN cases ON cases.id=documents.case_id
                WHERE documents.id=? AND expires_at>? AND (kind='quote' OR case_version=cases.version)
            ''', (token_hash(access_id), int(time.time()))).fetchone()
        if not row:
            raise HTTPException(404, 'Document not found.')
        offer = json.loads(row['offer'])
        if 'catalog_quote' in offer:
            quote = offer['catalog_quote']
            pdf = render_catalog_quote(quote['offer'], quote['customer'], quote['quantity'], quote['source_date'],
                                       font_path, approved=True, inn=quote['inn'])
        else:
            pdf = render_pdf(row['kind'], offer, font_path)
        return Response(pdf, media_type='application/pdf', headers={
            'Content-Disposition': f'attachment; filename="{row["kind"]}.pdf"',
            'Referrer-Policy': 'no-referrer',
            'Cache-Control': 'no-store',
        })

    @app.get(PREFIX + '/manager/cases', dependencies=[Depends(manager)])
    def queue(state: Literal['pending', 'all'] = 'pending', limit: int = Query(default=50, ge=1, le=100),
              offset: int = Query(default=0, ge=0)):
        with store.connect() as db:
            rows = db.execute("SELECT * FROM cases WHERE (?='all' OR state='pending') ORDER BY rowid DESC LIMIT ? OFFSET ?",
                              (state, limit, offset)).fetchall()
            cases = []
            for row in rows:
                context = chat_state(db, row['id'])
                cases.append({**case_view(row), 'reason': context.get('queue_reason'), 'quote': context.get('quote') if context.get('queue_reason') == 'quote_review' else None})
            return {'cases': cases}

    @app.get(PREFIX + '/manager/cases/{case_id}/messages', dependencies=[Depends(manager)])
    def manager_messages(case_id: str, after: int | None = Query(default=None, ge=0)):
        with store.connect() as db:
            get_case(db, case_id)
            return {'messages': read_chat_messages(db, case_id, after)}

    @app.post(PREFIX + '/manager/cases/{case_id}/decision', dependencies=[Depends(manager)])
    def decide(case_id: str, decision: Decision):
        with store.connect(write=True) as db:
            row = get_case(db, case_id)
            if row['decision_key'] == str(decision.request_id):
                if row['decision_choice'] != decision.choice or row['version'] != decision.version + 1 or row['decision_note'] != decision.note:
                    raise HTTPException(409, 'Request ID was already used.')
                result = case_view(row)
                if chat_only:
                    entry = db.execute("SELECT document_url FROM chat_messages WHERE case_id=? AND role='manager' ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
                    result['document_url'] = entry['document_url'] if entry else None
                return result
            if row['state'] != 'pending' or row['version'] != decision.version:
                raise HTTPException(409, 'This request has changed. Reload the case.')
            offer = json.loads(row['offer'])
            approved = decision.choice == 'approve'
            state = 'approved' if approved else 'rejected'
            payment_due = due_date(offer) if approved and not chat_only else None
            db.execute('''
                UPDATE cases SET state=?, version=version+1, payment_due=?, decision_key=?, decision_choice=?, decision_note=? WHERE id=?
            ''', (state, payment_due, str(decision.request_id), decision.choice, decision.note, case_id))
            append_event(db, case_id, 'manager_decision', state)
            if chat_only:
                context = chat_state(db, case_id)
                quote = context.get('quote') if context.get('queue_reason') == 'quote_review' else None
                document_url = None
                if approved and quote:
                    token = secrets.token_urlsafe(32)
                    db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)', (
                        token_hash(token), case_id, 'quote', json.dumps({'catalog_quote': quote}),
                        int(time.time()) + DOCUMENT_TTL, row['version'] + 1,
                    ))
                    document_url = f'{PREFIX}/documents/{token}'
                    append_event(db, case_id, 'catalog_quote_sent')
                default = 'Коммерческое предложение готово.' if document_url else 'Менеджер рассмотрел запрос.'
                save_chat_message(db, case_id, 'manager', decision.note.strip() or default, document_url=document_url)
                return {**case_view(get_case(db, case_id)), 'document_url': document_url}
            if approved and smtp_host:
                offer['payment_due'] = due_date(offer)
                queue_mail(db, case_id, 'approved', offer)
            return case_view(get_case(db, case_id))

    @app.post(PREFIX + '/manager/cases/{case_id}/rule', dependencies=[Depends(manager)])
    def create_rule(case_id: str, payload: RuleConfirmation):
        if chat_only:
            raise HTTPException(409, 'Automatic deferral rules are disabled in chat-only mode.')
        if not payload.confirmed:
            raise HTTPException(422, 'Confirm creation of a contract rule.')
        with store.connect(write=True) as db:
            row = get_case(db, case_id)
            if row['state'] != 'approved' or row['decision_choice'] != 'approve':
                raise HTTPException(409, 'A manual approval is required.')
            offer = json.loads(row['offer'])
            existing = db.execute('SELECT * FROM rules WHERE customer=? AND contract_ref=?', (offer['customer'], offer['contract_ref'])).fetchone()
            if existing and existing['source_case'] != case_id:
                raise HTTPException(409, 'This contract already has a rule.')
            if not existing:
                db.execute('INSERT INTO rules VALUES(?,?,?,?,?,?)', (
                    offer['customer'], offer['contract_ref'], offer['requested_days'], offer['renewal_total_kopecks'], row['decision_note'], case_id,
                ))
                append_event(db, case_id, 'contract_rule_saved', offer['contract_ref'])
            return {'contract_ref': offer['contract_ref'], 'days': offer['requested_days'], 'source_case': case_id}

    @app.get(PREFIX + '/manager/knowledge', dependencies=[Depends(manager)])
    def knowledge():
        with store.connect() as db:
            rows = db.execute('SELECT * FROM rules ORDER BY rowid DESC LIMIT 50').fetchall()
        return {'rules': [dict(row) for row in rows]}

    @app.get(PREFIX + '/manager/cases/{case_id}/journal', dependencies=[Depends(manager)])
    def journal(case_id: str):
        with store.connect() as db:
            get_case(db, case_id)
            events = db.execute('SELECT event,detail,created FROM journal WHERE case_id=? ORDER BY id', (case_id,)).fetchall()
            usage = db.execute('SELECT input_tokens,output_tokens,cost_microrubles FROM model_usage WHERE case_id=? AND input_tokens IS NOT NULL ORDER BY id', (case_id,)).fetchall()
            messages = read_chat_messages(db, case_id)
        return {'events': [dict(e) for e in events], 'usage': [dict(u) for u in usage], 'messages': messages}

    return app


def deployment_app():
    return create_app(Path(os.environ['SUPPORT_DATABASE']), Path(os.environ.get('SUPPORT_SCENARIO_PATH', DEMO_SOURCE)))
