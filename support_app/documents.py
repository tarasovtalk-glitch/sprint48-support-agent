from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
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
