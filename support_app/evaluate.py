import argparse
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

from .chat import chat_price, intent_cues, lookup, offer_id_from_url, run_turn, tool_request
from .scenario import load_scenario
from .store import Store


LINE = re.compile(r'^#(\d+)\s+\[([^\]]+)\]\s+(?:\[(store\.softline\.ru[^\]]*)\]\s*)?(.+)$', re.I)


def input_records(archive: Path):
    seen = set()
    with ZipFile(archive) as source:
        for file in source.infolist():
            if not re.fullmatch(r'buy_part_\d+_masked\.txt', PurePosixPath(file.filename).name):
                continue
            if file.file_size > 2_000_000:
                raise ValueError('One archive member exceeds the text limit.')
            for raw in source.read(file).decode('utf-8-sig').splitlines():
                if not raw.strip():
                    continue
                match = LINE.fullmatch(raw)
                if match is None:
                    raise ValueError(f'Unexpected record structure in {file.filename}')
                number, label, page, text = match.groups()
                if number not in seen:
                    seen.add(number)
                    yield label, text, page or ''


def outcome(state, reply, buttons):
    if state.get('queue_reason'):
        return 'manager_queue'
    if state.get('coupon_percent'):
        return 'demo_coupon'
    if any(x in reply for x in ('docs.softline.com/', 'store.softline.ru/delivery_info', 'login.softline.ru')):
        return 'knowledge_link'
    if any(action == 'select_offer' for _, action, _ in buttons):
        return 'catalog_options'
    if state.get('flow'):
        return 'clarification'
    return 'fallback_operator_offered'


def evaluate(archive: Path, catalog: Path, model_decisions: dict[int, tuple[str, str | None]] | None = None) -> dict:
    if not catalog.is_file():
        raise FileNotFoundError(catalog)
    fixture = load_scenario(Path(__file__).with_name('demo.json')).offer()
    totals = Counter()
    by_topic = {}
    manager_reasons = Counter()
    needs_model = 0
    qualifies = 0
    same_card_with_price = 0
    with TemporaryDirectory() as temp:
        store = Store(Path(temp) / 'evaluation.sqlite3')
        for index, (topic, text, page) in enumerate(input_records(archive)):
            state = {}
            needs_model += bool(tool_request(text, None, '', state) or intent_cues(text))
            hint, tool = (model_decisions or {}).get(index, ('unknown', None))
            case_id = uuid4().hex
            with store.connect(write=True) as db:
                db.execute('INSERT INTO cases(id,client_hash,offer) VALUES(?,?,?)', (case_id, case_id, json.dumps(fixture)))
                case = db.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
                reply, buttons = run_turn(db, case, state, catalog, text=text, page_url=page, intent_hint=hint, tool=tool)
            result = outcome(state, reply, buttons)
            totals[result] += 1
            if result == 'manager_queue':
                manager_reasons[state['queue_reason']] += 1
            source_offer = offer_id_from_url(page)
            if result == 'catalog_options' and source_offer and state.get('offered_ids') == [source_offer]:
                product = lookup(catalog, source_offer)
                if product and product['price_kopecks'] and product['url']:
                    price = chat_price(product['price_kopecks'])
                    if any(f' — {price} ' in line and product['url'] in line for line in reply.splitlines()):
                        same_card_with_price += 1
            if result == 'knowledge_link' or (result == 'catalog_options' and ' ₽' in reply and 'https://store.softline.ru/' in reply):
                qualifies += 1
            by_topic.setdefault(topic, Counter())[result] += 1
    return {
        'mode': 'offline_first_turn' if model_decisions is None else 'live_model_first_turn_replay',
        'records': sum(totals.values()), 'outcomes': dict(totals), 'manager_reasons': dict(manager_reasons),
        'clarification_counts_persisted_dialogue_only': True,
        'by_input_label': {topic: dict(items) for topic, items in sorted(by_topic.items())},
        'model_calls': 0, 'first_turns_with_model_decision': len(model_decisions or {}),
        'first_turns_eligible_for_model': needs_model,
        'first_turns_matching_exact_source_card_and_price': same_card_with_price,
        'first_turns_matching_resolution_rule': qualifies, 'manual_acceptance': None,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run local first-turn evaluation on anonymized support samples.')
    parser.add_argument('archive', type=Path)
    parser.add_argument('catalog', type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.archive, args.catalog), ensure_ascii=False, indent=2))
