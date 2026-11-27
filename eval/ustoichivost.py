# Проверка устойчивости (CME 295, лекция 7, MaxxBench): чуть меняем формулировку клиента —
# опечатка, заглавные буквы, лишние вежливые слова, без знаков препинания, латиница/кириллица —
# и смотрим, тот же ли товар находит поиск. Детерминированно, без модели и сети.
# Запуск: python eval/ustoichivost.py <catalog.sqlite3> <nabor.jsonl>
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support_app.dialog import find_family, words  # noqa: E402


def typo(text: str, rnd: random.Random) -> str:
    """Перестановка двух соседних букв в самом длинном слове (типичная опечатка при быстром наборе)."""
    ws = re.findall(r'[^\W\d_]{6,}', text)
    if not ws:
        return text
    w = max(ws, key=len)
    i = rnd.randrange(1, len(w) - 2)
    return text.replace(w, w[:i] + w[i + 1] + w[i] + w[i + 2:], 1)


KEYS = 'йцукенгшщзхъ фывапролджэ ячсмитьбю qwertyuiop asdfghjkl zxcvbnm'.split()


def _mutate(text: str, rnd: random.Random, how: str) -> str:
    ws = re.findall(r'[^\W\d_]{6,}', text)
    if not ws:
        return text
    w = max(ws, key=len)
    i = rnd.randrange(1, len(w) - 1)
    if how == 'drop':
        new = w[:i] + w[i + 1:]
    elif how == 'double':
        new = w[:i] + w[i] + w[i:]
    else:  # соседняя клавиша
        row = next((k for k in KEYS if w[i].lower() in k), None)
        if not row:
            return text
        j = row.index(w[i].lower())
        new = w[:i] + row[j + 1 if j + 1 < len(row) else j - 1] + w[i + 1:]
    return text.replace(w, new, 1)


VARIANTS = {
    'опечатка': lambda t, r: typo(t, r),
    'пропущена буква': lambda t, r: _mutate(t, r, 'drop'),
    'двойная буква': lambda t, r: _mutate(t, r, 'double'),
    'соседняя клавиша': lambda t, r: _mutate(t, r, 'key'),
    'заглавные': lambda t, r: t.upper(),
    'вежливость': lambda t, r: 'Здравствуйте, коллеги! ' + t + ' Заранее спасибо, жду ответа.',
    'без знаков': lambda t, r: re.sub(r'[^\w\s]', ' ', t),
    'без приветствия': lambda t, r: re.sub(r'^(добрый день|здравствуйте)[!.,\s]*', '', t, flags=re.I),
}


def top(db, text):
    family, conf, _, _ = find_family(db, words(text), text)
    return family[0]['family'] if family and conf >= 0.5 else None


def main():
    db = sqlite3.connect(sys.argv[1])
    db.row_factory = sqlite3.Row
    rnd = random.Random(295)
    total, same, diffs = 0, 0, []
    per = {k: [0, 0] for k in VARIANTS}
    for line in open(sys.argv[2], encoding='utf-8'):
        d = json.loads(line)
        text = d['turns'][0]['client']
        base = top(db, text)
        for name, fn in VARIANTS.items():
            variant = fn(text, rnd)
            if variant == text:
                continue
            got = top(db, variant)
            total += 1
            per[name][1] += 1
            if got == base:
                same += 1
                per[name][0] += 1
            else:
                diffs.append((d['id'], name, variant[:80]))
    print(f'вариантов: {total}, тот же товар: {same} ({same / total:.0%})')
    for name, (ok, n) in per.items():
        print(f'  {name}: {ok}/{n}')
    for x in diffs[:25]:
        print('  расхождение:', *x)
    return 0


if __name__ == '__main__':
    sys.exit(main())
