import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import AliasChoices, BaseModel, Field, StrictBool, model_validator

from .catalog import purchasable_units
from .knowledge import all_answers, question_for, save_answer
from .chat import buttons, customer_text, intent_cues, run_turn, tool_request
from .documents import render_catalog_quote, render_pdf, rubles
from .mail import run_mail_queue
from .model import choose_tool, classify
from .scenario import load_scenario
from .selection import catalog_router
from .jury import create_jury_store
from .store import (
    Store, append_event, case_view, chat_state, queue_mail,
    read_chat_messages, save_chat_message, save_chat_state,
)


PREFIX = '/support/api'
DOCUMENT_TTL = 15 * 60
PUBLIC_DEMO_REQUESTS_PER_MINUTE = 10
DEMO_SOURCE = Path(__file__).with_name('demo.json')


class Message(BaseModel):
    text: str | None = Field(default=None, max_length=20000)
    action: Literal['price', 'quote', 'invoice', 'deferral', 'placement', 'focus', 'term',
                    'deployment', 'select_offer', 'handoff', 'more_discount'] | None = None
    value: str = Field(default='', max_length=32)
    page_url: str = Field(default='', max_length=600)
    channel: Literal['chat', 'email', 'call_demo'] = 'chat'

    @model_validator(mode='after')
    def one_input(self):
        if (self.text is None) == (self.action is None):
            raise ValueError('Provide exactly one of text or action.')
        if self.text is not None and len(self.text) > 1000:
            # длинное письмо клиента не отклоняем ошибкой: берём начало, где обычно сам вопрос
            self.text = self.text[:1000].rsplit(' ', 1)[0]
        return self


class Decision(BaseModel):
    choice: Literal['approve', 'reject']
    version: int = Field(ge=0)
    request_id: UUID
    note: str = Field(default='', max_length=400, validation_alias=AliasChoices('reply', 'note'))
    remember: bool = False  # сохранить ответ менеджера в базу знаний: следующий клиент с тем же вопросом получит его сразу


class RuleConfirmation(BaseModel):
    confirmed: StrictBool


class KnowledgeEntry(BaseModel):
    confirmed: StrictBool
    question: str | None = Field(default=None, max_length=1000)
    answer: str | None = Field(default=None, max_length=1000)


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
    key_path = database.with_name('support-access-keys.json')
    access_keys = json.loads(key_path.read_text(encoding='utf-8')) if key_path.is_file() else {}
    if not isinstance(access_keys, dict) or any(
        not re.fullmatch(r'[a-f0-9]{64}', digest) or role not in ('admin', 'manager', 'jury')
        for digest, role in access_keys.items()
    ):
        raise ValueError('Invalid cabinet access key configuration.')
    jury_directory = TemporaryDirectory(prefix='support-jury-') if 'jury' in access_keys.values() else None
    jury_store = create_jury_store(Path(jury_directory.name) / 'sample.sqlite3') if jury_directory else None
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
            if jury_directory:
                jury_directory.cleanup()

    app = FastAPI(title='SMF Support', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    catalog_path = Path(os.environ.get('SUPPORT_CATALOG_DATABASE', database.with_name('catalog.sqlite3')))
    app.include_router(catalog_router(catalog_path, demo_key, font_path, require_key), prefix=PREFIX)

    def cabinet_role(x_manager_key: str = Header(default='')) -> str:
        role = access_keys.get(token_hash(x_manager_key)) if 24 <= len(x_manager_key) <= 128 else None
        if role:
            return role
        if access_keys and len(manager_key) < 24:
            raise HTTPException(401, 'Access key required.')
        require_key(manager_key, x_manager_key)
        return 'admin'

    def cabinet_reader(role: str = Depends(cabinet_role)) -> Store:
        if role == 'jury':
            if jury_store is None:
                raise HTTPException(503, 'Jury samples are unavailable.')
            return jury_store
        return store

    def manager(role: str = Depends(cabinet_role)):
        if role == 'jury':
            raise HTTPException(403, 'Jury access is read only.')

    def admin(role: str = Depends(cabinet_role)):
        if role != 'admin':
            raise HTTPException(403, 'Administrator access is required.')

    def client(authorization: str = Header(default='')) -> str:
        prefix, _, token = authorization.partition(' ')
        if prefix.lower() != 'bearer' or not 30 <= len(token) <= 64:
            raise HTTPException(401, 'Session token required.')
        with store.connect() as db:
            row = db.execute('SELECT id FROM cases WHERE client_hash=?', (token_hash(token),)).fetchone()
        if row is None:
            raise HTTPException(401, 'Session token required.')
        return row['id']

    def public_demo(x_smf_public_key: str = Header(default=''), x_smf_public_ip: str = Header(default='')) -> bool:
        if not chat_only or len(demo_key) < 24 or not secrets.compare_digest(demo_key.encode(), x_smf_public_key.encode()):
            return False
        try:
            address = ipaddress.ip_address(x_smf_public_ip)
        except ValueError as error:
            raise HTTPException(400, 'Invalid demo request.') from error
        if isinstance(address, ipaddress.IPv6Address):
            network = ipaddress.ip_network((address, 64), strict=False)
            visitor = str(address.ipv4_mapped or network)
        else:
            visitor = str(address)
        identifier = hmac.digest(demo_key.encode(), visitor.encode(), 'sha256').hex()
        now = int(time.time())
        with store.connect(write=True) as db:
            db.execute('DELETE FROM public_demo_requests WHERE requested_at <= ?', (now - 60,))
            count, oldest = db.execute('''
                SELECT COUNT(*), MIN(requested_at) FROM public_demo_requests WHERE client_hash=?
            ''', (identifier,)).fetchone()
            if count >= PUBLIC_DEMO_REQUESTS_PER_MINUTE:
                retry_after = str(max(1, oldest + 60 - now))
                raise HTTPException(429, 'Demo request limit reached.', headers={'Retry-After': retry_after})
            db.execute('INSERT INTO public_demo_requests(client_hash,requested_at) VALUES (?,?)', (identifier, now))
        return True

    @app.get(PREFIX + '/health', status_code=204)
    def health():
        with store.connect() as db:
            db.execute('SELECT 1')
        return Response(status_code=204)

    @app.post(PREFIX + '/sessions', status_code=201)
    def session(x_demo_key: str = Header(default=''), public: bool = Depends(public_demo)):
        if not public:
            require_key(demo_key, x_demo_key)
        session_token = secrets.token_urlsafe(32)
        case_id = uuid4().hex
        with store.connect(write=True) as db:
            db.execute('INSERT INTO cases(id,client_hash,offer) VALUES(?,?,?)', (case_id, token_hash(session_token), json.dumps(scenario.offer())))
            append_event(db, case_id, 'opened', scenario.source)
            view = case_view(get_case(db, case_id), use_fixture=not chat_only)
        return {'session_token': session_token, 'case': view}

    @app.get(PREFIX + '/case')
    def my_case(case_id: str = Depends(client)):
        with store.connect() as db:
            return case_view(get_case(db, case_id), use_fixture=not chat_only)

    @app.get(PREFIX + '/case/messages')
    def client_messages(after: int | None = Query(default=None, ge=0), case_id: str = Depends(client)):
        with store.connect() as db:
            return {'messages': read_chat_messages(db, case_id, after)}

    @app.post(PREFIX + '/case/messages', dependencies=[Depends(public_demo)])
    def message(payload: Message, case_id: str = Depends(client)):
        if chat_only:
            if payload.channel != 'chat':
                raise HTTPException(422, 'This stand accepts chat messages only.')
            with store.connect() as db:
                existing_context = chat_state(db, case_id)
            plan = tool_request(payload.text or '', payload.action, payload.value, existing_context)
            model_options = {'api_key': model_key, 'model_uri': model_uri, 'daily': daily_limit, 'total': total_limit}
            selected_tool = choose_tool(store, case_id, *plan, **model_options) if plan else None
            cues = intent_cues(payload.text) if payload.text and not existing_context.get('awaiting_customer') else ''
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
                        'case': case_view(get_case(db, case_id), use_fixture=False), 'messages': [client_entry, agent_entry]}
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
                                       font_path, approved=True, inn=quote['inn'], kpp=quote.get('kpp', ''))
        else:
            pdf = render_pdf(row['kind'], offer, font_path)
        return Response(pdf, media_type='application/pdf', headers={
            'Content-Disposition': f'attachment; filename="{row["kind"]}.pdf"',
            'Referrer-Policy': 'no-referrer',
            'Cache-Control': 'no-store',
        })

    @app.get(PREFIX + '/manager/access')
    def manager_access(role: str = Depends(cabinet_role)):
        return {'role': role}

    @app.get(PREFIX + '/manager/metrics')
    def manager_metrics(reader: Store = Depends(cabinet_reader)):
        with reader.connect() as db:
            cases = db.execute('SELECT COUNT(*) FROM cases').fetchone()[0]
            calls, input_tokens, output_tokens, cost = db.execute('''
                SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0),
                       COALESCE(SUM(cost_microrubles), 0)
                FROM model_usage WHERE input_tokens IS NOT NULL
            ''').fetchone()
        return {'cases': cases, 'model_calls': calls, 'input_tokens': input_tokens,
                'output_tokens': output_tokens, 'cost_microrubles': cost,
                'sample': reader is jury_store}

    @app.get(PREFIX + '/manager/cases')
    def queue(state: Literal['pending', 'all'] = 'pending', limit: int = Query(default=50, ge=1, le=100),
              offset: int = Query(default=0, ge=0), reader: Store = Depends(cabinet_reader)):
        with reader.connect() as db:
            rows = db.execute('''
                SELECT c.*,
                    COALESCE((SELECT j.created FROM journal j WHERE j.case_id=c.id AND j.event='opened' ORDER BY j.id LIMIT 1),
                             (SELECT m.created FROM chat_messages m WHERE m.case_id=c.id ORDER BY m.id LIMIT 1)) AS created,
                    (SELECT m.created FROM chat_messages m WHERE m.case_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_message,
                    (SELECT m.text FROM chat_messages m WHERE m.case_id=c.id AND m.role='client' ORDER BY m.id LIMIT 1) AS first_client_message
                FROM cases c
                WHERE (?='all' OR c.state='pending') ORDER BY c.rowid DESC LIMIT ? OFFSET ?
            ''', (state, limit, offset)).fetchall()
            cases = []
            for row in rows:
                context = chat_state(db, row['id'])
                cases.append({**case_view(row, use_fixture=not chat_only), 'reason': context.get('queue_reason'),
                              'quote': context.get('quote') if context.get('queue_reason') == 'quote_review' else None,
                              'created': row['created'], 'updated': row['last_message'] or row['created'],
                              'first_client_message': row['first_client_message']})
            return {'cases': cases}

    @app.get(PREFIX + '/manager/cases/{case_id}/messages')
    def manager_messages(case_id: str, after: int | None = Query(default=None, ge=0), reader: Store = Depends(cabinet_reader)):
        with reader.connect() as db:
            get_case(db, case_id)
            return {'messages': read_chat_messages(db, case_id, after)}

    @app.post(PREFIX + '/manager/cases/{case_id}/decision', dependencies=[Depends(manager)])
    def decide(case_id: str, decision: Decision):
        with store.connect(write=True) as db:
            row = get_case(db, case_id)
            if row['decision_key'] == str(decision.request_id):
                if row['decision_choice'] != decision.choice or row['version'] != decision.version + 1 or row['decision_note'] != decision.note:
                    raise HTTPException(409, 'Request ID was already used.')
                result = case_view(row, use_fixture=not chat_only)
                if chat_only:
                    entry = db.execute("SELECT document_url FROM chat_messages WHERE case_id=? AND role='manager' ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
                    result['document_url'] = entry['document_url'] if entry else None
                return result
            if row['state'] != 'pending' or row['version'] != decision.version:
                raise HTTPException(409, 'This request has changed. Reload the case.')
            offer = json.loads(row['offer'])
            approved = decision.choice == 'approve'
            context = chat_state(db, case_id) if chat_only else {}
            quote = context.get('quote') if context.get('queue_reason') == 'quote_review' else None
            if approved and quote and 'requested_users' not in quote:
                if purchasable_units(quote['offer'], quote['quantity']) != quote['quantity']:
                    raise HTTPException(409, 'The draft quantity needs review. Reject this draft and start a new quote.')
            state = 'approved' if approved else 'rejected'
            payment_due = due_date(offer) if approved and not chat_only else None
            db.execute('''
                UPDATE cases SET state=?, version=version+1, payment_due=?, decision_key=?, decision_choice=?, decision_note=? WHERE id=?
            ''', (state, payment_due, str(decision.request_id), decision.choice, decision.note, case_id))
            append_event(db, case_id, 'manager_decision', state)
            if chat_only:
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
                if decision.remember and decision.note.strip():
                    remember_answer(db, case_id, None, decision.note)
                return {**case_view(get_case(db, case_id), use_fixture=False), 'document_url': document_url}
            if approved and smtp_host:
                offer['payment_due'] = due_date(offer)
                queue_mail(db, case_id, 'approved', offer)
            return case_view(get_case(db, case_id))

    @app.post(PREFIX + '/manager/cases/{case_id}/rule', dependencies=[Depends(admin)])
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

    def remember_answer(db, case_id: str, question: str | None, answer: str | None) -> dict:
        messages = read_chat_messages(db, case_id)
        if not answer:
            row = get_case(db, case_id)
            last = next((m['text'] for m in reversed(messages) if m['role'] == 'manager'), '')
            answer = row['decision_note'] or last
        try:
            entry = save_answer(db, case_id, question or question_for(messages), answer or '')
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        append_event(db, case_id, 'knowledge_saved', str(entry['id']))
        return entry

    @app.post(PREFIX + '/manager/cases/{case_id}/knowledge', dependencies=[Depends(manager)])
    def save_knowledge(case_id: str, payload: KnowledgeEntry):
        if not payload.confirmed:
            raise HTTPException(422, 'Confirm saving the answer to the knowledge base.')
        with store.connect(write=True) as db:
            get_case(db, case_id)
            return remember_answer(db, case_id, payload.question, payload.answer)

    @app.get(PREFIX + '/manager/knowledge')
    def knowledge(reader: Store = Depends(cabinet_reader)):
        with reader.connect() as db:
            rows = db.execute('SELECT * FROM rules ORDER BY rowid DESC LIMIT 50').fetchall()
            answers = all_answers(db) if reader is store else []
        return {'rules': [dict(row) for row in rows], 'answers': answers}

    @app.get(PREFIX + '/manager/cases/{case_id}/journal')
    def journal(case_id: str, reader: Store = Depends(cabinet_reader)):
        with reader.connect() as db:
            get_case(db, case_id)
            events = db.execute('SELECT event,detail,created FROM journal WHERE case_id=? ORDER BY id', (case_id,)).fetchall()
            usage = db.execute('SELECT input_tokens,output_tokens,cost_microrubles FROM model_usage WHERE case_id=? AND input_tokens IS NOT NULL ORDER BY id', (case_id,)).fetchall()
            messages = read_chat_messages(db, case_id)
        return {'events': [dict(e) for e in events], 'usage': [dict(u) for u in usage], 'messages': messages}

    return app


def deployment_app():
    return create_app(Path(os.environ['SUPPORT_DATABASE']), Path(os.environ.get('SUPPORT_SCENARIO_PATH', DEMO_SOURCE)))
