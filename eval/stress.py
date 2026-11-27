# Стресс-проверка стабильности (программный оценщик, без модели; CME 295, лекция 7).
# Для каждой реплики клиента: ответ 200 и не пустой, не больше одного вопроса, и каждый показанный товар
# связан со словами клиента (общая основа слова) — иначе это «случайный товар». Ответ по разделу каталога
# («Для задачи …») и закреплённые правила (подпись → КриптоПро) считаются связанными.
# Плюс искажения (опечатки, без знаков) и мусорный ввод.
# Запуск: python eval/stress.py <catalog.sqlite3> <набор.jsonl> [ещё наборы...]
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'eval'))
from local import Chat, make_client  # noqa: E402
import sqlite3  # noqa: E402
from support_app.dialog import ALIASES, ESIGN, GENERIC, LICENSE_WORDS, SKU, fix_typos, normalize, stem, words  # noqa: E402

PRODUCT_LINE = re.compile(r'^(?:—\s*|Принял:\s*|Нашёл в каталоге:\s*)?(.+?)\s—\s[\d\s  ]+(?:,\d+)?\s?₽', re.M)
JUNK = ['', '   ', '???', '🙂🙂🙂', 'а', '1234567890', '"; DROP TABLE products; --', 'NEAR(a b) OR * AND "', '<script>alert(1)</script>',
        'ыыыыыыыыыыыыыыыыыыы', 'Нужна лицензия ' * 300, 'цена?' * 50, '%%%', 'select * from', '\n\n\n', 'ok', 'Спасибо']
ANALOG_FRAME = re.compile(r'Аналоги, которые есть в каталоге|Самые доступные варианты')
SYNONYM_OK = {'kaspersky', 'криптопро', 'microsoft', 'windows', 'office', 'astra', 'alse', 'anydesk', 'multifactor', 'рутокен'}


def turns_of(d):
    for t in d.get('turns', []):
        yield t['client'] if isinstance(t, dict) else t


def keys(text):
    out = set()
    for w in words(text):
        if w.isdigit() or LICENSE_WORDS.match(w) or GENERIC.fullmatch(w) or len(w) < 3:
            continue
        out.add(stem(w)[:6])
    return out


def typo(text, rnd):
    ws = text.split()
    idx = [i for i, w in enumerate(ws) if len(w) >= 6 and w.isalpha()]
    if not idx:
        return text
    i = rnd.choice(idx)
    w = ws[i]
    j = rnd.randrange(1, len(w) - 2)
    ws[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return ' '.join(ws)


def check(client, dialogs, db):
    stats = {'реплик': 0, 'ошибок HTTP': 0, 'пустых': 0, 'два вопроса': 0, 'случайный товар': 0}
    bad = []
    for name, turns in dialogs:
        chat, said = Chat(client), ''
        for t in turns:
            r = chat.say(t)
            stats['реплик'] += 1
            if chat.last.status_code != 200:
                stats['ошибок HTTP'] += 1
                bad.append((name, 'HTTP', t[:80], str(chat.last.status_code)))
                continue
            reply = r.get('reply') or ''
            said += ' ' + t
            if not reply.strip():
                stats['пустых'] += 1
                bad.append((name, 'пусто', t[:80], ''))
            if re.sub(r'https?://\S+', '', reply).count('?') > 1:   # «?» в ссылке — не вопрос
                stats['два вопроса'] += 1
                bad.append((name, 'два вопроса', t[:80], reply[:160]))
            if 'Для задачи «' in reply or ANALOG_FRAME.search(reply) or 'store.softline.ru' in said or SKU.search(normalize(said)):
                continue   # раздел каталога, аналог по таблице замен, ссылка или артикул — связь задана явно
            fixed = fix_typos(db, said)
            asked = keys(fixed) | ({'alse', 'astra'} if re.search(r'astra|астр|alse', normalize(fixed)) else set())
            asked |= {out for _, outs in ALIASES for out in outs.split() if out in normalize(' '.join(words(fixed)))}
            for m in PRODUCT_LINE.finditer(reply):
                product = m.group(1)
                if re.match(r'На \d+ шт', product):
                    continue
                pk = keys(product) | {w for w in SYNONYM_OK if w in normalize(product).replace('крипто про', 'криптопро')}
                if 'криптопро' in normalize(product) and ESIGN.search(normalize(said)):
                    continue
                if not (pk & asked):
                    stats['случайный товар'] += 1
                    bad.append((name, 'случайный товар', said.strip()[-120:], product[:90]))
                    break
    return stats, bad


def main():
    client = make_client(Path(sys.argv[1]))
    db = sqlite3.connect(sys.argv[1])
    db.row_factory = sqlite3.Row
    base = []
    for f in sys.argv[2:]:
        for line in open(f, encoding='utf-8'):
            d = json.loads(line)
            base.append((d['id'], list(turns_of(d))))
    rnd = random.Random(27)
    variants = [(n + '/опечатка', [typo(t, rnd) for t in ts]) for n, ts in base]
    variants += [(n + '/без знаков', [re.sub(r'[^\w\s]', ' ', t) for t in ts]) for n, ts in base]
    junk = [(f'мусор{i}', [j]) for i, j in enumerate(JUNK)]
    total_bad = 0
    for label, ds in (('исходные', base), ('искажения', variants), ('мусорный ввод', junk)):
        stats, bad = check(client, ds, db)
        total_bad += stats['ошибок HTTP'] + stats['пустых'] + stats['случайный товар']
        print(label + ':', stats)
        for b in bad[:25]:
            print('  ', ' | '.join(b))
    return 1 if total_bad else 0


if __name__ == '__main__':
    sys.exit(main())
