"""Сводка передачи для менеджера: одна строка — почему передано и что уже известно, чтобы не перечитывать весь диалог."""
import csv
import io

REASONS = {
    'quote_review': 'Черновик КП на проверку', 'price_confirmation': 'Сверить цену и количество', 'not_in_catalog': 'Товара нет в каталоге',
    'order_question': 'Вопрос по заказу', 'activation_problem': 'Не активируется ключ', 'discount_over_limit': 'Скидка больше 5%',
    'tender': 'Тендер или госзакупка', 'customer_request': 'Клиент просит менеджера', 'request_status': 'Статус заявки',
    'payment_question': 'Вопрос оплаты', 'needs_manager': 'Нужен менеджер', 'deferral': 'Просит отсрочку', 'model_routing': 'Не распознан запрос',
    'complaint': 'Жалоба клиента', 'closing_documents': 'Закрывающие документы', 'analog_request': 'Нужен аналог',
    'exact_product_request': 'Нужен именно этот товар', 'server_license': 'Серверная лицензия', 'catalog_unavailable': 'Каталог недоступен',
    'quote_multi': 'Черновик КП на проверку',
}
STATES = {'pending': 'Ждёт менеджера', 'approved': 'Одобрено', 'rejected': 'Отклонено', 'open': 'Открыто', 'closed': 'Закрыто'}


def term_label(value) -> str:
    if str(value) == '0':
        return 'бессрочно'
    try:
        n = int(value)
    except (TypeError, ValueError):
        return f'{value} месяцев'
    a, b = n % 10, n % 100
    word = 'месяц' if a == 1 and b != 11 else 'месяца' if 2 <= a <= 4 and not 12 <= b <= 14 else 'месяцев'
    return f'{n} {word}'


def reason_text(reason: str | None) -> str:
    if not reason:
        return ''
    return REASONS.get(reason, 'Подбор или аналог' if reason.replace('_', '').isalpha() and reason.islower() and '_' not in reason else 'Передано менеджеру')


def handoff_facts(context: dict, offer_name: str | None) -> list[list[str]]:
    facts = []
    quote = (context.get('quote_frozen') or context.get('quote') or {}) if context.get('queue_reason') == 'quote_review' else {}
    name = (quote.get('offer') or {}).get('name') or offer_name
    if name:
        facts.append(['Позиция', name[:120]])
    if quote.get('amount_kopecks'):
        amount = f'{quote["amount_kopecks"] / 100:,.2f}'.replace(',', ' ').replace('.', ',')
        facts.append(['Сумма по каталогу', f'{amount} ₽' + (f', купон {quote["discount_percent"]}%' if quote.get('discount_percent') else '')])
    elif context.get('coupon_percent'):
        facts.append(['Купон', f'{context["coupon_percent"]}%'])
    count = (quote.get('requested_users') or quote.get('quantity')) if quote else context.get('quantity')
    if count and not quote.get('items'):
        facts.append(['Количество', str(count)])
    if context.get('term') is not None and context.get('term') != '':
        facts.append(['Срок', term_label(context['term']) + (' (по умолчанию)' if context.get('term_assumed') else '')])
    known = [label for key, label in (('customer', 'организация'), ('inn', 'ИНН'), ('kpp', 'КПП')) if context.get(key)]
    if known:
        facts.append(['Реквизиты', ', '.join(known)])
    return facts


def handoff_summary(context: dict, offer_name: str | None, last_client: str | None) -> str:
    parts = []
    if context.get('queue_reason'):
        parts.append('Причина: ' + reason_text(context['queue_reason']))
    for label, value in handoff_facts(context, offer_name):
        parts.append(f'{label}: {value}')
    if last_client:
        parts.append('Последнее от клиента: «' + ' '.join(last_client.split())[:200] + '»')
    return '. '.join(parts)


def safe_cell(value) -> str:
    """Ячейка CSV не начинается с = + - @: таблица не выполнит её как формулу."""
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip(' \t\r\n')[:1] in ('=', '+', '-', '@') or text[:1] in ('\t', '\r', '\n') else text


def cases_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    out.write('﻿')  # Excel открывает кириллицу без настройки
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['Обращение', 'Состояние', 'Причина', 'Создано', 'Обновлено', 'Первая реплика клиента', 'Сводка'])
    for row in rows:
        writer.writerow([safe_cell(v) for v in (row.get('id'), STATES.get(row.get('state'), row.get('state')), reason_text(row.get('reason')),
                                                row.get('created'), row.get('updated'), row.get('first_client_message'), row.get('summary'))])
    return out.getvalue()
