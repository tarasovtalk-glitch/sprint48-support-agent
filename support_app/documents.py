from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


def rubles(kopecks: int) -> str:
    whole, cents = divmod(kopecks, 100)
    return f'{whole:,}'.replace(',', ' ') + f',{cents:02d} руб.'


def render_pdf(kind: str, offer: dict, font_path: Path) -> bytes:
    pdfmetrics.registerFont(TTFont('SupportDocument', str(font_path)))
    buffer = BytesIO()
    page = Canvas(buffer, pagesize=A4)
    title = 'Коммерческое предложение' if kind == 'quote' else 'Черновик счёта'
    page.setTitle(title)
    page.setFont('SupportDocument', 18)
    page.drawString(50, 775, title)
    page.setFont('SupportDocument', 11)
    lines = [
        'ДЕМОНСТРАЦИОННЫЙ ОБРАЗЕЦ. БЕЗ ОПЛАТЫ.',
        f'Покупатель: {offer["customer"]}',
        f'Заказ для продления: {offer["previous_order"]}',
        f'Позиция: {offer["product"]}',
        f'Количество: {offer["quantity"]}',
        f'Цена за единицу: {rubles(offer["renewal_unit_kopecks"])}',
        f'Сумма: {rubles(offer["renewal_total_kopecks"])}',
        f'Цена действует до: {offer["price_until"]}',
    ]
    if offer.get('payment_due'):
        lines.append(f'Оплатить до: {offer["payment_due"]}')
    elif kind == 'invoice':
        lines.append('Условия отсрочки требуют решения менеджера.')
    for index, line in enumerate(lines):
        page.drawString(50, 735 - index * 23, line)
    page.save()
    return buffer.getvalue()


def render_catalog_quote(offer: dict, customer: str, packages: int, source_date: str, font_path: Path) -> bytes:
    pdfmetrics.registerFont(TTFont('SupportDocument', str(font_path)))
    buffer = BytesIO()
    page = Canvas(buffer, pagesize=A4)
    page.setTitle('Черновик коммерческого предложения')
    page.setFont('SupportDocument', 18)
    page.drawString(50, 775, 'Коммерческое предложение')
    page.setFont('SupportDocument', 11)
    price = offer['price_kopecks']
    lines = [
        'ЧЕРНОВИК ДЛЯ ПРОВЕРКИ МЕНЕДЖЕРОМ',
        f'Куда: {customer}',
        f'Артикул: {offer["sku"]}',
        f'Наименование: {offer["name"]}',
        f'Кол-во выбранных позиций каталога: {packages}',
        f'Цена за позицию по фиду: {rubles(price)}',
        f'Сумма по фиду: {rubles(price * packages)}',
        'В т.ч. НДС: уточняется менеджером.',
        'Срок поставки и срок действия: уточняются менеджером.',
        f'Источник цены: каталог Softline {source_date}.',
    ]
    y = 735
    for line in lines:
        for segment in simpleSplit(line, 'SupportDocument', 11, 480):
            page.drawString(50, y, segment)
            y -= 17
        y -= 5
    page.save()
    return buffer.getvalue()
