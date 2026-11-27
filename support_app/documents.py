"""PDF коммерческого предложения и черновика счёта в фирменном стиле Softline.

Вёрстка — reportlab platypus: шапка с логотипом, стороны сделки, таблица позиций, итог, условия, подвал.
Шрифт — из SUPPORT_PDF_FONT; жирное начертание ищется рядом (DejaVuSans-Bold, «Arial Bold», arialbd),
иначе всё набирается обычным. Цены и суммы приходят из каталога — шаблон их не пересчитывает, кроме скидки по купону.
"""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from .catalog import discounted

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LOGO = Path(__file__).with_name('assets') / 'softline-logo.png'
BRAND = colors.HexColor('#a20c33')      # малиновый Softline
BRAND_SOFT = colors.HexColor('#f8e9ed')
INK = colors.HexColor('#1f2024')
SLATE = colors.HexColor('#505866')
MUTED = colors.HexColor('#6b6f76')
LINE = colors.HexColor('#dcdde2')
HEAD_BG = colors.HexColor('#f2f3f5')
SITE = 'store.softline.ru'


def rubles(kopecks: int) -> str:
    whole, cents = divmod(kopecks, 100)
    return f'{whole:,}'.replace(',', ' ') + f',{cents:02d} руб.'


def _fonts(font_path: Path) -> tuple[str, str]:
    pdfmetrics.registerFont(TTFont('SupportDocument', str(font_path)))
    stem, folder = font_path.stem, font_path.parent
    for name in (f'{stem}-Bold.ttf', f'{stem} Bold.ttf', f'{stem}bd.ttf', f'{stem}-bold.ttf'):
        bold = folder / name
        if bold.is_file():
            pdfmetrics.registerFont(TTFont('SupportDocumentBold', str(bold)))
            return 'SupportDocument', 'SupportDocumentBold'
    return 'SupportDocument', 'SupportDocument'


def _styles(regular: str, bold: str) -> dict:
    base = ParagraphStyle('base', fontName=regular, fontSize=9.5, leading=13.5, textColor=INK)
    return {
        'small': ParagraphStyle('small', parent=base, fontSize=8, leading=11, textColor=MUTED),
        'small_r': ParagraphStyle('small_r', parent=base, fontSize=8, leading=11, textColor=MUTED, alignment=TA_RIGHT),
        'label': ParagraphStyle('label', parent=base, fontName=bold, fontSize=7.5, leading=10, textColor=MUTED),
        'title': ParagraphStyle('title', parent=base, fontName=bold, fontSize=21, leading=25, textColor=INK),
        'status': ParagraphStyle('status', parent=base, fontName=bold, fontSize=8, leading=11, textColor=BRAND),
        'cell': ParagraphStyle('cell', parent=base, fontSize=9, leading=12.5),
        'cell_b': ParagraphStyle('cell_b', parent=base, fontName=bold, fontSize=9, leading=12.5),
        'head': ParagraphStyle('head', parent=base, fontName=bold, fontSize=8, leading=10.5, textColor=SLATE),
        'num': ParagraphStyle('num', parent=base, fontSize=9, leading=12.5, alignment=TA_RIGHT),
        'num_head': ParagraphStyle('num_head', parent=base, fontName=bold, fontSize=8, leading=10.5, textColor=SLATE, alignment=TA_RIGHT),
        'total_label': ParagraphStyle('total_label', parent=base, fontSize=9.5, leading=13, alignment=TA_RIGHT, textColor=SLATE),
        'total': ParagraphStyle('total', parent=base, fontName=bold, fontSize=9.5, leading=13, alignment=TA_RIGHT),
        'grand_label': ParagraphStyle('grand_label', parent=base, fontName=bold, fontSize=11, leading=15, alignment=TA_RIGHT),
        'grand': ParagraphStyle('grand', parent=base, fontName=bold, fontSize=13, leading=16, alignment=TA_RIGHT, textColor=BRAND),
    }


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _footer(regular: str, title: str):
    def draw(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(BRAND)
        canvas.rect(0, height - 3 * mm, width, 3 * mm, stroke=0, fill=1)
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, 16 * mm, width - 18 * mm, 16 * mm)
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 11.5 * mm, f'Softline Store · {SITE} · документ подготовил агент поддержки')
        canvas.drawRightString(width - 18 * mm, 11.5 * mm, f'{title} · лист {doc.page}')
        canvas.restoreState()
    return draw


def _header(st: dict, title: str, status: str) -> list:
    logo = Image(str(LOGO), width=62 * mm, height=62 * mm * 229 / 1588) if LOGO.is_file() else _p('Софтлайн', st['title'])
    right = [_p(SITE, st['small_r']), _p('Магазин программного обеспечения', st['small_r'])]
    top = Table([[logo, right]], colWidths=[100 * mm, 74 * mm])
    top.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('LINEBELOW', (0, 0), (-1, 0), 0.8, LINE),
                             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 9)]))
    badge = Table([[_p(status, st['status'])]], colWidths=[pdfmetrics.stringWidth(status, st['status'].fontName, 8) + 16])
    badge.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BRAND_SOFT), ('LEFTPADDING', (0, 0), (-1, -1), 7),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 3),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    badge.hAlign = 'LEFT'
    return [top, Spacer(1, 9 * mm), _p(title, st['title']), Spacer(1, 3 * mm), badge, Spacer(1, 7 * mm)]


def _parties(st: dict, rows: list) -> Table:
    cells = [[_p(label.upper(), st['label']) for label, _ in rows],
             [[_p(line, st['cell_b'] if i == 0 else st['cell']) for i, line in enumerate(lines)] for _, lines in rows]]
    table = Table(cells, colWidths=[87 * mm] * len(rows))
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 0),
                               ('BOTTOMPADDING', (0, 0), (-1, 0), 3)]))
    return table


def _items(st: dict, rows: list) -> Table:
    head = [_p('№', st['head']), _p('Наименование', st['head']), _p('Кол-во', st['num_head']),
            _p('Цена', st['num_head']), _p('Сумма', st['num_head'])]
    body = [[_p(number, st['cell']), [_p(name, st['cell_b']), _p(code, st['small'])],
             _p(quantity, st['num']), _p(price, st['num']), _p(total, st['num'])]
            for number, name, code, quantity, price, total in rows]
    table = Table([head] + body, colWidths=[9 * mm, 88 * mm, 17 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_BG), ('LINEBELOW', (0, 0), (-1, 0), 0.8, SLATE),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, LINE), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def _totals(st: dict, lines: list) -> Table:
    data = [[_p(label, st['grand_label'] if grand else st['total_label']), _p(value, st['grand'] if grand else st['total'])]
            for label, value, grand in lines]
    table = Table(data, colWidths=[124 * mm, 50 * mm])
    style = [('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
             ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]
    for index, (_, _, grand) in enumerate(lines):
        if grand:
            style += [('LINEABOVE', (1, index), (1, index), 1.2, BRAND), ('TOPPADDING', (0, index), (-1, index), 7)]
    table.setStyle(TableStyle(style))
    return table


def _conditions(st: dict, lines: list) -> Table:
    table = Table([[_p('УСЛОВИЯ', st['label'])]] + [[_p(line, st['cell'])] for line in lines], colWidths=[174 * mm])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), HEAD_BG), ('LINEBEFORE', (0, 0), (0, -1), 2.2, BRAND),
                               ('LEFTPADDING', (0, 0), (-1, -1), 10), ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5), ('TOPPADDING', (0, 0), (-1, 0), 8),
                               ('BOTTOMPADDING', (0, -1), (-1, -1), 8)]))
    return table


def _build(title: str, story: list, regular: str) -> bytes:
    buffer = BytesIO()
    # Offset the frame padding so the tables align with the 18 mm page margins.
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm - 6, rightMargin=18 * mm - 6,
                            topMargin=15 * mm,
                            bottomMargin=22 * mm, title=title, author='Softline Store', subject=title)
    footer = _footer(regular, title)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_pdf(kind: str, offer: dict, font_path: Path) -> bytes:
    regular, bold = _fonts(font_path)
    st = _styles(regular, bold)
    title = 'Коммерческое предложение' if kind == 'quote' else 'Черновик счёта'
    story = _header(st, title, 'ДЕМОНСТРАЦИОННЫЙ ОБРАЗЕЦ. БЕЗ ОПЛАТЫ.')
    story += [_parties(st, [('Поставщик', ['ПАО «Софтлайн»', SITE]),
                            ('Покупатель', [offer['customer'], f'Заказ для продления: {offer["previous_order"]}'])]),
              Spacer(1, 7 * mm),
              _items(st, [['1', offer['product'], 'Продление', str(offer['quantity']),
                           rubles(offer['renewal_unit_kopecks']), rubles(offer['renewal_total_kopecks'])]]),
              Spacer(1, 3 * mm), _totals(st, [('Сумма:', rubles(offer['renewal_total_kopecks']), True)]), Spacer(1, 7 * mm)]
    terms = [f'Цена действует до: {offer["price_until"]}']
    if offer.get('payment_due'):
        terms.append(f'Оплатить до: {offer["payment_due"]}')
    elif kind == 'invoice':
        terms.append('Условия отсрочки требуют решения менеджера.')
    story.append(KeepTogether(_conditions(st, terms)))
    return _build(title, story, regular)


def _ru_date(value: str) -> str:
    """2026-11-27 → 27.11.2026; иное — как есть."""
    text = str(value or '')
    return '.'.join(reversed(text[:10].split('-'))) if len(text) >= 10 and text[4] == '-' and text[7] == '-' else text


def render_catalog_quote(offer: dict, customer: str, packages: int, source_date: str, font_path: Path, *, approved=False, inn='', kpp='',
                         discount: int = 0, items: list | None = None, invoice: bool = False) -> bytes:
    regular, bold = _fonts(font_path)
    st = _styles(regular, bold)
    title = 'Черновик счёта' if invoice else 'Коммерческое предложение'
    status = 'ДЕМОНСТРАЦИОННОЕ КП. ПРЕДОПЛАТА ПО ОФЕРТЕ.' if approved else 'ЧЕРНОВИК ДЛЯ ПРОВЕРКИ МЕНЕДЖЕРОМ'
    if invoice:
        status = 'ДЕМОНСТРАЦИОННЫЙ РАСЧЁТ. ПОСТАВКУ УТОЧНИТ МЕНЕДЖЕР.'
    story = _header(st, title, status)
    buyer = [customer] + ([f'ИНН: {inn}'] if inn else []) + ([f'КПП: {kpp}'] if kpp else [])
    story += [_parties(st, [('Поставщик', ['ПАО «Софтлайн»', SITE]), ('Покупатель', buyer)]), Spacer(1, 7 * mm)]

    rows, total = [], 0
    for index, item in enumerate(items or [dict(offer, quantity=packages)], 1):
        line_total = item['price_kopecks'] * item['quantity']
        total += line_total
        code = f'Артикул: {item["sku"]}' if item.get('sku') else f'ID предложения в фиде: {item["id"]}. Артикул не указан.'
        rows.append([str(index), item['name'], code, str(item['quantity']), rubles(item['price_kopecks']), rubles(line_total)])
    story.append(_items(st, rows))

    lines = [('Сумма по фиду:', rubles(total), not discount)]
    if discount:
        after = discounted(total, discount)
        lines += [(f'Скидка по купону {discount}%:', '−' + rubles(total - after), False), ('Итого со скидкой:', rubles(after), True)]
    story += [Spacer(1, 3 * mm), _totals(st, lines), Spacer(1, 7 * mm),
              KeepTogether(_conditions(st, [
                  'В т.ч. НДС: уточняется менеджером.',
                  'Срок поставки и срок действия: уточняются менеджером.',
                  f'Источник цены: каталог Softline {_ru_date(source_date)}.',
              ]))]
    return _build(title, story, regular)
