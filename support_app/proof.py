"""Страница проверки для жюри: GET /support/api/proof — итоги прогона и живые цифры стенда, без входа.

Итоги прогона — из proof.json рядом (обновляется после каждого полного прогона набора и атак).
Живые цифры — из той же базы, что видит кабинет: только счётчики, без текстов и данных клиентов.
"""
import html
import json
from pathlib import Path

RUN = Path(__file__).with_name('proof.json')
LOGO = Path(__file__).with_name('assets') / 'softline-logo.svg'


def load_run() -> dict:
    return json.loads(RUN.read_text(encoding='utf-8'))


def group3(n) -> str:
    return f'{int(n or 0):,}'.replace(',', ' ')


def seconds(ms) -> str:
    return 'пока нет ответов' if ms is None else f'{ms / 1000:.2f}'.replace('.', ',') + ' с'


def render(run: dict, live: dict) -> str:
    e = lambda s: html.escape(str(s))
    pct = round(100 * run['ok'] / run['auto']) if run['auto'] else 0
    catalog = live.get('catalog') or {}
    rows = [
        ('Реплики, сверяемые автоматически', f'{run["ok"]} из {run["auto"]} ({pct} %)', 'ответ совпал с эталоном: товар, цена, сумма, шаг'),
        ('Реплики с ошибкой', run['bad'], 'нет цены, не тот вариант или шаг; сумм не из каталога нет'),
        ('КП и причины передачи', run['cabinet'], 'проверяются в кабинете менеджера, в верные не входят'),
        ('Весь диалог без единой ошибки', f'{run["strict"]} из {run["dialogues"]}', 'строгая мерка: одна неточная реплика — диалог не засчитан'),
        ('Опасные ошибки', run['dangerous'], 'сумма не из каталога, скидка больше 5 %'),
        ('Атаки OWASP Top 10 for LLM 2025', f'{run["attacks_ok"]} из {run["attacks"]}',
         (f'прогон {run["attacks_run"]}; ' if run.get('attacks_run') else '') + 'без утечки инструкций, чужих данных, цены не из каталога'),
        ('Медиана ответа на наборе', f'{run["median_s"]} с', f'{run["replies"]} реплик'),
    ]
    table = ''.join(f'<tr><td>{e(a)}</td><td class="n">{e(b)}</td><td>{e(c)}</td></tr>' for a, b, c in rows)
    live_rows = [
        ('Обращений на стенде', group3(live.get('cases'))),
        ('Закрыл агент без менеджера', group3(live.get('closed_by_agent'))),
        ('Передал менеджеру', group3(live.get('handed_to_manager'))),
        ('Агент отвечает за (медиана)', seconds(live.get('agent_reply_median_ms'))),
        ('Вызовов модели', group3(live.get('model_calls'))),
        (f'В продаже с ценой, фид {".".join(reversed(catalog.get("source_date", "")[:10].split("-")))}' if catalog else 'Каталог',
         group3(catalog.get('priced_available')) if catalog else 'не загружен'),
    ]
    logo = LOGO.read_text(encoding='utf-8') if LOGO.is_file() else '<b>Софтлайн</b>'
    live_html = ''.join(f'<div class="box"><div class="big">{e(v)}</div><div>{e(k)}</div></div>' for k, v in live_rows)
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Проверка агента поддержки Softline Store</title><style>
:root{{color-scheme:light}}body{{margin:0;background:#fff;color:#1f2024;font:16px/1.5 Roboto,Inter,Arial,system-ui,sans-serif;border-top:6px solid #a20c33}}
main{{max-width:980px;margin:0 auto;padding:20px 16px 48px}}.head{{display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:1px solid #dcdde2;padding-bottom:12px;margin-bottom:22px;font-size:13px;color:#a20c33;font-weight:600;text-transform:uppercase;letter-spacing:.04em}}.head svg{{height:34px;width:auto;display:block}}h1{{font-size:30px;line-height:1.2;margin:0 0 8px;color:#1f2024;letter-spacing:-.01em}}
h2{{font-size:19px;margin:28px 0 10px;color:#1f2024}}.lead{{color:#45484f;margin:0 0 8px}}.sub{{color:#6b6f76;font-size:14px}}
table{{width:100%;border-collapse:collapse;font-size:15px}}th{{text-align:left;background:#f2f3f5;border-bottom:2px solid #a6a8ab;padding:7px 8px}}
td{{border-bottom:1px solid #e6e7eb;padding:7px 8px;vertical-align:top}}td.n{{text-align:right;font-weight:700;white-space:nowrap}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
.box{{border:1px solid #dcdde2;border-top:3px solid #a20c33;border-radius:6px;padding:12px 14px;background:#f4f4f6}}.big{{font-size:22px;font-weight:700;color:#a20c33}}
ol li{{margin:6px 0}}code{{background:#f2f3f5;padding:1px 5px;border-radius:4px}}a{{color:#a20c33}}
@media (max-width:640px){{table,thead,tbody,tr,td,th{{display:block}}th{{display:none}}td{{border:0;padding:2px 0}}tr{{border-bottom:1px solid #e6e7eb;padding:8px 0}}td.n{{text-align:left}}}}
</style></head><body><main>
<div class="head">{logo}<span>Команда SMF · задача №6</span></div>
<h1>Проверка агента поддержки Softline Store</h1>
<p class="lead">Цены и суммы считает код по каталогу, модель выбирает шаги. Персональные данные в модель не уходят.</p>
<h2>Итоги прогона — версия {e(run["version"])}, {e(run["date"])}</h2>
<p class="sub">Набор: {run["dialogues"]} диалог / {run["replies"]} реплик клиента из реальных обращений выгрузки, эталон ответа на каждую реплику.</p>
<table><tr><th>Мерка</th><th>Результат</th><th>Что значит</th></tr>{table}</table>
<h2>Живые цифры этого стенда</h2>
<p class="sub">Считаются при открытии страницы, без проверочных обращений набора.</p>
<div class="grid">{live_html}</div>
<h2>Проверить самому за 5 минут</h2><ol>
<li>Чат <a href="/support/">analyzebot.ru/support/</a>: «Нужно КП на 19 бессрочных лицензий КриптоПро» → «Рабочие места» → 70&nbsp;300&nbsp;₽ по каталогу.</li>
<li>«Нужно защитить почту и файлы на 50 сотрудников» → «И почта, и файлы» → «12 месяцев» → «Свои серверы» → «А российский аналог?».</li>
<li>Кабинет <a href="/support/cabinet/#journal">analyzebot.ru/support/cabinet/</a> — ключ жюри в форме сдачи. Видны шаги агента и токены по каждому обращению.</li>
<li>Код и тесты: <code>python -m pytest -q</code>, набор — <code>eval/</code>.</li></ol>
</main></body></html>'''
