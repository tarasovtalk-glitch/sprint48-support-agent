# Строгая проверка цен в ответах агента (программный оценщик, без модели).
# Каждая сумма «N ₽» в ответе должна объясняться каталогом: цена позиции × целое количество,
# в том числе со скидкой не больше 5 %. Позиции берутся из ссылок на карточки в том же ответе;
# если ссылок нет — из всех позиций, уже названных в разговоре.
# Запуск: python eval/ceny.py <catalog.sqlite3> <run.jsonl> [out.json]
import json
import re
import sqlite3
import sys

PRICE = re.compile(r'(\d{1,3}(?:[   ]\d{3})*(?:,\d{1,2})?)\s?₽')
CARD = re.compile(r'store\.softline\.ru/[^\s)]*?-(\d+)/')
MAX_DISCOUNT = 5


def kopecks(text: str) -> int:
    whole, _, frac = re.sub(r'[   ]', '', text).partition(',')
    return int(whole) * 100 + int((frac + '00')[:2])


def explained(amount: int, prices: set[int]) -> bool:
    for p in prices:
        if not p:
            continue
        for d in range(0, MAX_DISCOUNT + 1):
            factor = (100 - d) / 100
            n = amount / (p * factor)
            k = round(n)
            if k >= 1 and abs(amount - round(p * k * factor)) <= max(1, k):  # округление до копеек на каждой позиции
                return True
    return False


def sum_of_lines(text: str, prices: set[int]) -> int:
    """Сумма итогов по строкам вида «N. … — цена × k = итог» или «N. … — цена»."""
    total = 0
    for line in re.findall(r'^\d+\.\s.*$', text, re.M):
        sums = [kopecks(x) for x in PRICE.findall(line.split('Карточка:')[0])]
        if sums and explained(sums[-1], prices):
            total += sums[-1]
    return total


def agent_texts(turn: dict) -> list[str]:
    resp = turn.get('resp') or {}
    out = []
    for m in reversed(resp.get('messages') or []):
        if m.get('role') == 'client':
            break
        out.append(m.get('text') or '')
    return out or [resp.get('reply') or '']


def main():
    db = sqlite3.connect(sys.argv[1])
    price_of = dict(db.execute('SELECT id, price_kopecks FROM products WHERE price_kopecks IS NOT NULL'))
    by_name = {}
    for oid, name, price in db.execute('SELECT id, name, price_kopecks FROM products WHERE price_kopecks IS NOT NULL'):
        by_name.setdefault(name[:60], set()).add(price)
    rows, bad, total = [], 0, 0
    for line in open(sys.argv[2], encoding='utf-8'):
        rec = json.loads(line)
        seen: set[int] = set()
        for i, turn in enumerate(rec.get('turns', []), 1):
            text = ' '.join(agent_texts(turn))
            own = {price_of[i_] for i_ in CARD.findall(text) if i_ in price_of}
            for key, prices in by_name.items():
                if key in text:
                    own |= prices
            seen |= own
            found = [(m, kopecks(m.group(1))) for m in PRICE.finditer(text)]
            ok = [a for _, a in found if explained(a, own or seen)]
            for m, a in found:
                total += 1
                if explained(a, own or seen):
                    continue
                if re.search(r'Итого:\s*$', text[max(0, m.start() - 8):m.start()]) and a == sum_of_lines(text, own or seen):
                    continue  # общий итог = сумма строк, каждая из которых сверена с каталогом
                bad += 1
                rows.append({'id': rec['id'], 'turn': i, 'amount': m.group(0), 'context': text[max(0, m.start() - 90):m.end() + 20]})
    result = {'sums': total, 'unexplained': bad, 'rows': rows}
    if len(sys.argv) > 3:
        json.dump(result, open(sys.argv[3], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'сумм в ответах: {total}, не объясняются каталогом: {bad}')
    for r in rows[:20]:
        print(' ', r['id'], r['turn'], r['amount'], '|', r['context'].replace('\n', ' / '))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
