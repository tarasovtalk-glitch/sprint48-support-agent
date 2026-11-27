# Замер поиска по каталогу (CME 295, лекция 6: Recall@k и MRR на таблице «запрос → товар»).
# Эталон берётся из набора: ref.offer_prices (ID позиций) или ref.family (регулярное выражение по названию).
# Отдельно — «нет в каталоге»: на таких запросах поиск не должен уверенно найти чужой товар.
# Запуск: python eval/poisk.py <catalog.sqlite3> <nabor.jsonl>
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support_app.dialog import find_family, words  # noqa: E402


def ranked(db, text):
    """Семьи в порядке ответа агента: первая — та, что вернул поиск, дальше — остальные кандидаты по баллу."""
    scores = []
    family, conf, _, _ = find_family(db, words(text), text, ranking=scores)
    top = family[0]['family'] if family and conf >= 0.5 else None
    order = [top] if top else []
    for _, fam in sorted(scores, key=lambda x: -x[0]):
        if fam not in order:
            order.append(fam)
    sellable = bool(family) and any(o['available'] and o['price_kopecks'] for o in family)
    return order, top, sellable


def main():
    db = sqlite3.connect(sys.argv[1])
    db.row_factory = sqlite3.Row
    pos, neg = [], []
    for line in open(sys.argv[2], encoding='utf-8'):
        d = json.loads(line)
        ref, first = d.get('ref') or {}, d['turns'][0]
        text = first['client']
        ids = list((ref.get('offer_prices') or {}).keys())
        gold = {r[0] for r in db.execute(f"SELECT family FROM products WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else set()
        if not gold and ref.get('family'):
            rx = re.compile(ref['family'], re.I)
            gold = {r['family'] for r in db.execute('SELECT family, name FROM products') if rx.search(r['name'])}
        exp = first['expect']
        opts = exp.get('options', [exp])
        missing = any(o['action'] == 'analog' or o.get('handoff_reason') == 'not_in_catalog' for o in opts)
        if gold:
            order, top, _ = ranked(db, text)
            rank = next((i for i, f in enumerate(order, 1) if f in gold), None) if top else None
            pos.append((d['id'], rank, top))
        elif missing:
            order, top, sellable = ranked(db, text)
            neg.append((d['id'], bool(top) and sellable, top))
    n = len(pos)
    r1 = sum(1 for _, r, _ in pos if r == 1) / n
    r3 = sum(1 for _, r, _ in pos if r and r <= 3) / n
    mrr = sum(1 / r for _, r, _ in pos if r) / n
    false_hits = [i for i, hit, _ in neg if hit]
    print(f'запросов с эталоном: {n}; Recall@1 {r1:.0%}, Recall@3 {r3:.0%}, MRR {mrr:.2f}')
    print('мимо (место эталона):', [(i, r) for i, r, _ in pos if r != 1])
    print(f'«нет в каталоге»: {len(neg)} запросов, уверенно нашёл чужой товар: {len(false_hits)} {false_hits}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
