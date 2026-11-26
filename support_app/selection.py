import re
from contextlib import closing
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .catalog import (
    EXPANSION_OR_MEDIA, KASPERSKY_ENDPOINT_SKU, KASPERSKY_FAMILIES, KASPERSKY_MAIL_SKU,
    find_matches, normalize, read_only, tiered_annual_offer, view,
)
from .documents import render_catalog_quote


SOURCE_LINKS = {
    'help_center': 'https://docs.softline.com/ru-ru',
    'delivery': 'https://store.softline.ru/delivery_info/',
}
QUESTIONS = {
    'product': 'Как называется продукт или версия, которую вы рассматриваете?',
    'users': 'Сколько пользователей, устройств или почтовых ящиков нужно покрыть?',
    'term_months': 'На какой срок нужна лицензия?',
    'deployment': 'Какое развёртывание подходит: облачное, на своих серверах или оба варианта?',
    'task': 'Что нужно сделать или защитить? Например, почту, рабочие станции или файлы.',
}
TOPICS = (
    ('Почта', r'почт|антиспам|mail\b', KASPERSKY_MAIL_SKU, (('mail', 'security'), ('антиспам',))),
    ('Рабочие станции и файлы', r'файл|рабоч.*станц|устройств|антивирус|endpoint', KASPERSKY_ENDPOINT_SKU, (('endpoint', 'security'), ('dr', 'web', 'enterprise'))),
)


class Selection(BaseModel):
    mode: Literal['known', 'needs']
    query: str = Field(min_length=1, max_length=300)
    product: str = Field(default='', max_length=100)
    users: int | None = Field(default=None, ge=1, le=100_000)
    term_months: int | None = Field(default=None, ge=1, le=120)
    deployment: Literal['cloud', 'local', 'flexible'] | None = None
    require_registry: bool = False


class DraftQuote(BaseModel):
    offer_id: str = Field(min_length=1, max_length=32)
    packages: int = Field(ge=1, le=10_000)
    customer: str = Field(min_length=1, max_length=100)


def shortlist(rows: list[dict], users: int | None, require_registry: bool, *, distinct_families=False) -> list[dict]:
    unique = {}
    for row in rows:
        if require_registry and not row['registry']:
            continue
        identifier = row['family'] if distinct_families else row['id']
        unique.setdefault(identifier, row)
    result = list(unique.values())
    for row in result:
        row['users_match_confirmed'] = users is not None and row['max_users'] is not None
        row['can_draft_quote'] = bool(row['available'] and row['price_kopecks'] and row['sku'])
    return result[:4]


def selection_result(db, req: Selection) -> dict:
    user_match = re.search(r'\b(\d{1,5})\s*(?:сотрудник|пользовател|устройств|узл|ящик|мест)', normalize(req.query))
    users = req.users or (int(user_match.group(1)) if user_match else None)
    term = req.term_months or (12 if re.search(r'\bна год\b|\b12\s*мес', normalize(req.query)) else None)
    missing = [key for key, value in [('users', users), ('term_months', term), ('deployment', req.deployment)] if not value]
    sources = dict(db.execute('SELECT name,value FROM metadata').fetchall())
    result = {'questions': [], 'groups': [], 'sources': {**SOURCE_LINKS, **sources}, 'needs_confirmation': []}
    if req.mode == 'known':
        if not req.product.strip():
            missing.insert(0, 'product')
        else:
            purchase = not re.search(EXPANSION_OR_MEDIA, normalize(req.query))
            exact = find_matches(db, [req.product], users, term, new_purchase_only=purchase)
            family = req.product.split()[0]
            if not exact:
                base = 'MDaemon Messaging Server' if normalize(family) == 'mdaemon' else family
                candidates = find_matches(db, [base], users, term, new_purchase_only=purchase)
            else:
                candidates = exact
            offers = shortlist(candidates, users, req.require_registry)
            if offers:
                result['groups'].append({'topic': req.product, 'exact_terms_found': bool(exact), 'offers': offers})
            if not exact:
                result['needs_confirmation'].append('Указанная версия не найдена по точным словам. Варианты требуют сверки.')
    else:
        matched_topics = [topic for topic in TOPICS if re.search(topic[1], normalize(req.query))]
        if not matched_topics:
            missing.insert(0, 'task')
        if not missing:
            for title, _, family, searches in matched_topics:
                candidates = []
                if term == 12 and req.deployment in ('local', 'flexible'):
                    verified = tiered_annual_offer(db, family, users)
                    if verified:
                        candidates.append(verified)
                for terms in searches:
                    candidates.extend(
                        offer for offer in find_matches(db, list(terms), users, term, active_only=True, new_purchase_only=True)
                        if not (offer.get('sku') or '').upper().startswith(KASPERSKY_FAMILIES)
                        and 'curenet' not in normalize(offer['name'])
                    )
                offers = shortlist(candidates, users, req.require_registry, distinct_families=True)
                if offers:
                    result['groups'].append({'topic': title, 'exact_terms_found': None, 'offers': offers})
    if req.deployment and req.deployment != 'flexible':
        result['needs_confirmation'].append('Перед выбором подтвердите совместимость с указанным развёртыванием по карточке товара.')
    if req.require_registry and not result['groups'] and not missing:
        result['needs_confirmation'].append('В найденных предложениях нет подтверждённого номера реестра. Нужна дополнительная сверка.')
    result['questions'] = [{'field': key, 'text': QUESTIONS[key]} for key in missing]
    result['status'] = 'clarify' if missing else 'matches' if result['groups'] else 'review'
    return result


def catalog_router(path: Path, demo_key: str, font: Path, require_key) -> APIRouter:
    router = APIRouter(prefix='/catalog')

    def check(supplied):
        require_key(demo_key, supplied)
        if not path.is_file():
            raise HTTPException(503, 'Catalog import is not ready.')

    @router.post('/selection')
    def select(req: Selection, x_demo_key: str = Header(default='')):
        check(x_demo_key)
        with closing(read_only(path)) as db:
            return selection_result(db, req)

    @router.get('/products/{offer_id}')
    def product(offer_id: str, x_demo_key: str = Header(default='')):
        check(x_demo_key)
        with closing(read_only(path)) as db:
            row = db.execute('SELECT * FROM products WHERE id=?', (offer_id,)).fetchone()
            if row is None:
                raise HTTPException(404, 'Offer not found.')
            return view(row)

    @router.post('/quote')
    def quote(req: DraftQuote, x_demo_key: str = Header(default='')):
        check(x_demo_key)
        with closing(read_only(path)) as db:
            row = db.execute('SELECT * FROM products WHERE id=?', (req.offer_id,)).fetchone()
            if not row or not row['available'] or not row['sku'] or row['price_kopecks'] is None:
                raise HTTPException(422, 'The offer needs a confirmed price and SKU.')
            source = db.execute("SELECT value FROM metadata WHERE name='source_date'").fetchone()
            date = source['value'] if source else ''
            pdf = render_catalog_quote(dict(row), req.customer, req.packages, date, font)
        return Response(pdf, media_type='application/pdf', headers={
            'Content-Disposition': 'attachment; filename="softline-draft-quote.pdf"',
            'Cache-Control': 'no-store',
        })

    return router
