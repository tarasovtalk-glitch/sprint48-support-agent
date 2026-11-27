"""Мини-фид для тестов: категории + предложения семейств, которые встречаются в наборе диалогов.
Запуск: python tests/data/make_mini.py <полный feed.yml> tests/data/feed-mini.yml"""
import json, re, sys
from pathlib import Path

KEEP = re.compile(r'крипто\s*про|cryptopro|mdaemon|kaspersky|касперск|windows 11|microsoft office|office 20|office ltsc|'
                  r'contentreader|астра|astra|смоленск|vipnet|dr\.?\s*web|р7|r7-офис|мойофис|crypto\s*arm|криптоарм|'
                  r'indeed|1с|1c:|abbyy|adobe acrobat|secret net|континент|рутокен|рутокен|jacarta|positive|kerio|'
                  r'zoom|teamviewer|anydesk|autocad|компас|nanocad|ред ос|red os|alt linux|альт|eset|zabbix|veeam', re.I)
# семьи, нужные таблице поиска в тестах: основной Kaspersky для бизнеса и Multifactor
EXTRA = re.compile(r'Kaspersky Endpoint Security для бизнеса Стандартный|multifactor', re.I)
src, out = Path(sys.argv[1]), Path(sys.argv[2])
nabor = Path(__file__).resolve().parents[2] / 'eval' / 'nabor60.jsonl'
ids = set()
for line in open(nabor, encoding='utf-8'):
    ref = json.loads(line).get('ref') or {}
    ids |= set((ref.get('offer_prices') or {}).keys())
text = src.read_text(encoding='utf-8')
head, rest = text.split('<offers>', 1)
offers = re.findall(r'<offer .*?</offer>', rest, re.S)
from collections import Counter
per = Counter(); kept = []
for o in offers:
    oid = re.search(r'id="(\d+)"', o).group(1)
    m = KEEP.search(o.split('</name>')[0] + o.split('<vendor>')[1][:120])
    x = EXTRA.search(o.split('</name>')[0])
    if x and per['extra:' + x.group(0).lower()] < 60:
        per['extra:' + x.group(0).lower()] += 1
        ids.add(oid)
    if oid in ids or (m and 'available="true"' in o and per[m.group(0).lower()] < 120):
        if m: per[m.group(0).lower()] += 1
        o = re.sub(r'\s*<(?:picture|group_picture|oldprice|delivery|pickup)>.*?</(?:picture|group_picture|oldprice|delivery|pickup)>', '', o)
        o = re.sub(r'\s*<param name="(?:Примечание|Особенности доставки|Системные требования)">.*?</param>', '', o, flags=re.S)
        kept.append(o)
out.write_text(head + '<offers>\n' + '\n'.join(kept) + '\n</offers>\n</shop>\n</yml_catalog>\n', encoding='utf-8')
print(len(offers), '→', len(kept), 'предложений;', 'артикулов набора:', len(ids))
