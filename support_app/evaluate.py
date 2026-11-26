import argparse
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

from .chat import intent_cues, run_turn, tool_request
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
    if 'docs.softline.com/' in reply:
        return 'knowledge_link'
    if any(action == 'select_offer' for _, action, _ in buttons):
        return 'catalog_options'
    if state.get('flow'):
        return 'clarification'
    return 'fallback_operator_offered'


def evaluate(archive: Path, catalog: Path) -> dict:
    if not catalog.is_file():
        raise FileNotFoundError(catalog)
    fixture = load_scenario(Path(__file__).with_name('demo.json')).offer()
    totals = Counter()
    by_topic = {}
    needs_model = 0
    qualifies = 0
    with TemporaryDirectory() as temp:
        store = Store(Path(temp) / 'evaluation.sqlite3')
        for topic, text, page in input_records(archive):
            state = {}
            needs_model += bool(tool_request(text, None, '', state) or intent_cues(text))
            case_id = uuid4().hex
            with store.connect(write=True) as db:
                db.execute('INSERT INTO cases(id,client_hash,offer) VALUES(?,?,?)', (case_id, case_id, json.dumps(fixture)))
                case = db.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
                reply, buttons = run_turn(db, case, state, catalog, text=text, page_url=page)
            result = outcome(state, reply, buttons)
            totals[result] += 1
            if result == 'knowledge_link' or (result == 'catalog_options' and ' ₽' in reply and 'https://store.softline.ru/' in reply):
                qualifies += 1
            by_topic.setdefault(topic, Counter())[result] += 1
    return {
        'mode': 'offline_first_turn', 'records': sum(totals.values()), 'outcomes': dict(totals),
        'by_input_label': {topic: dict(items) for topic, items in sorted(by_topic.items())},
        'model_calls': 0, 'first_turns_eligible_for_model': needs_model,
        'first_turns_matching_resolution_rule': qualifies, 'manual_acceptance': None,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run local first-turn evaluation on anonymized support samples.')
    parser.add_argument('archive', type=Path)
    parser.add_argument('catalog', type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.archive, args.catalog), ensure_ascii=False, indent=2))
