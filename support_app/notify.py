"""Уведомление менеджеру в Telegram: новое обращение в очереди или черновик КП на проверку.

Включается переменными TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID; без них ничего не отправляется.
Telegram — зарубежный сервис, поэтому в сообщении нет персональных данных: ни имени, ни почты, ни телефона,
ни ИНН, ни текста клиента. Только причина передачи, сумма КП из каталога и ссылка в кабинет, где менеджер
видит обращение после входа. Отправка в фоне: сбой Telegram не задерживает и не ломает ответ клиенту.
"""
import json
import threading
from urllib.error import URLError
from urllib.request import Request, urlopen

from .documents import rubles
from .summary import REASONS

API = 'https://api.telegram.org'


def in_background(function, *args):
    threading.Thread(target=function, args=args, daemon=True).start()


def notice_text(case_id: str, reason: str, quote: dict | None, cabinet_url: str) -> str:
    lines = ['Новое обращение в очереди: ' + REASONS.get(reason, 'нужен менеджер') + '.']
    if quote and reason in ('quote_review', 'quote_multi') and quote.get('amount_kopecks'):
        positions = len(quote.get('items') or []) or 1
        lines.append(f'Черновик КП: {positions} поз., {rubles(quote["amount_kopecks"])} по каталогу — проверьте и подтвердите.')
    lines.append(f'Обращение {case_id[:8]}.')
    if cabinet_url:
        lines.append(cabinet_url.rstrip('/') + '/#queue')
    return '\n'.join(lines)


class Telegram:
    def __init__(self, token: str, chat_id: str, cabinet_url: str = '', opener=urlopen):
        self.token, self.chat_id, self.cabinet_url, self.opener = token.strip(), chat_id.strip(), cabinet_url, opener

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def deliver(self, text: str) -> bool:
        body = json.dumps({'chat_id': self.chat_id, 'text': text, 'disable_web_page_preview': True}).encode()
        request = Request(f'{API}/bot{self.token}/sendMessage', data=body, headers={'Content-Type': 'application/json'})
        try:
            with self.opener(request, timeout=10) as response:
                return bool(json.load(response).get('ok'))
        except (URLError, OSError, ValueError, AttributeError):
            return False

    def case_queued(self, case_id: str, reason: str, quote: dict | None, *, background: bool = True):
        if not self.enabled:
            return None
        text = notice_text(case_id, reason, quote, self.cabinet_url)
        if not background:
            return self.deliver(text)
        in_background(self.deliver, text)
        return None
