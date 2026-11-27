from io import BytesIO
from pathlib import Path

from .catalog import discounted

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


def render_catalog_quote(offer: dict, customer: str, packages: int, source_date: str, font_path: Path, *, approved=False, inn='', kpp='',
                         discount: int = 0, items: list | None = None, invoice: bool = False) -> bytes:
    pdfmetrics.registerFont(TTFont('SupportDocument', str(font_path)))
    buffer = BytesIO()
    page = Canvas(buffer, pagesize=A4)
    title = 'Черновик счёта' if invoice else 'Коммерческое предложение'
    page.setTitle(title)
    page.setFont('SupportDocument', 18)
    page.drawString(50, 775, title)
    page.setFont('SupportDocument', 11)
    price = offer['price_kopecks']
    head = ['ДЕМОНСТРАЦИОННОЕ КП. ПРЕДОПЛАТА ПО ОФЕРТЕ.' if approved else 'ЧЕРНОВИК ДЛЯ ПРОВЕРКИ МЕНЕДЖЕРОМ',
            'Поставщик: ПАО «Софтлайн»', f'Покупатель: {customer}']
    if invoice:
        head[0] = 'ДЕМОНСТРАЦИОННЫЙ РАСЧЁТ. ПОСТАВКУ УТОЧНИТ МЕНЕДЖЕР.'
    if items:  # несколько позиций одним КП
        body, total = [], 0
        for i, item in enumerate(items, 1):
            line_total = item['price_kopecks'] * item['quantity']
            total += line_total
            sku = f'артикул {item["sku"]}' if item.get('sku') else f'ID в фиде {item["id"]}'
            body.append(f'{i}. {item["name"]} ({sku}): {rubles(item["price_kopecks"])} × {item["quantity"]} = {rubles(line_total)}')
        body.append(f'Сумма по фиду: {rubles(total)}')
    else:
        total = price * packages
        body = [
            f'Артикул: {offer["sku"]}' if offer['sku'] else f'ID предложения в фиде: {offer["id"]}. Артикул не указан.',
            f'Наименование: {offer["name"]}',
            f'Количество: {packages}',
            f'Цена за позицию по фиду: {rubles(price)}',
            f'Сумма по фиду: {rubles(total)}',
        ]
    if discount:
        after = discounted(total, discount)
        body += [f'Скидка по купону {discount}%: −{rubles(total - after)}', f'Итого со скидкой: {rubles(after)}']
    lines = head + body + [
        'В т.ч. НДС: уточняется менеджером.',
        'Срок поставки и срок действия: уточняются менеджером.',
        f'Источник цены: каталог Softline {source_date}.',
    ]
    if inn:
        lines.insert(3, f'ИНН: {inn}')
    if kpp:
        lines.insert(4 if inn else 3, f'КПП: {kpp}')
    y = 735
    for line in lines:
        for segment in simpleSplit(line, 'SupportDocument', 11, 480):
            if y < 50:  # длинное КП — продолжаем на следующем листе
                page.showPage()
                page.setFont('SupportDocument', 11)
                y = 790
            page.drawString(50, y, segment)
            y -= 17
        y -= 5
    page.save()
    return buffer.getvalue()
