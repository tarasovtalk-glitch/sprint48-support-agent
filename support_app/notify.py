"""Уведомление менеджеру в Telegram или MAX: новое обращение в очереди или черновик КП на проверку.

Канал подключается переменными: Telegram — TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID, MAX — MAX_BOT_TOKEN и MAX_CHAT_ID.
Менеджер в кабинете включает и выключает уведомления и выбирает канал (настройки notify_on и notify_channel).
В сообщении нет персональных данных (Telegram — зарубежный сервис, правило одно для обоих каналов): ни имени, ни почты, ни телефона,
ни ИНН, ни текста клиента. Только причина передачи, сумма КП из каталога и ссылка в кабинет, где менеджер
видит обращение после входа. Отправка в фоне: сбой Telegram не задерживает и не ломает ответ клиенту.
"""
import json
import threading
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .documents import rubles
from .summary import REASONS

API = 'https://api.telegram.org'
MAX_API = 'https://platform-api2.max.ru'  # dev.max.ru/docs-api: домен platform-api2, токен в заголовке Authorization


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


class Channel:
    id, name = '', ''

    def __init__(self, token: str, chat_id: str, cabinet_url: str = '', opener=urlopen):
        self.token, self.chat_id, self.cabinet_url, self.opener = token.strip(), chat_id.strip(), cabinet_url, opener

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def deliver(self, text: str) -> bool:
        raise NotImplementedError

    def case_queued(self, case_id: str, reason: str, quote: dict | None, *, background: bool = True):
        if not self.enabled:
            return None
        text = notice_text(case_id, reason, quote, self.cabinet_url)
        if not background:
            return self.deliver(text)
        in_background(self.deliver, text)
        return None


class Telegram(Channel):
    id, name = 'telegram', 'Telegram'

    def deliver(self, text: str) -> bool:
        body = json.dumps({'chat_id': self.chat_id, 'text': text, 'disable_web_page_preview': True}).encode()
        request = Request(f'{API}/bot{self.token}/sendMessage', data=body, headers={'Content-Type': 'application/json'})
        try:
            with self.opener(request, timeout=10) as response:
                return bool(json.load(response).get('ok'))
        except (URLError, OSError, ValueError, AttributeError):
            return False


class Max(Channel):
    """MAX Bot API: POST /messages?chat_id=…, токен в заголовке Authorization, успех — объект message в ответе.
    chat_id группы приходит событием bot_added, когда бота добавляют в чат (GET /updates или подписка)."""
    id, name = 'max', 'MAX'

    def deliver(self, text: str) -> bool:
        body = json.dumps({'text': text, 'notify': True}).encode()
        request = Request(f'{MAX_API}/messages?chat_id={quote(self.chat_id)}&disable_link_preview=true', data=body,
                          headers={'Authorization': self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener(request, timeout=10) as response:
                return isinstance(json.load(response).get('message'), dict)
        except (URLError, OSError, ValueError, AttributeError):
            return False


class Notifier:
    """Каналы уведомлений и выбор менеджера: включено ли и куда писать."""

    def __init__(self, *channels: Channel):
        self.channels = {c.id: c for c in channels}

    def default_channel(self) -> str:
        return next((c.id for c in self.channels.values() if c.enabled), next(iter(self.channels)))

    def view(self, on: str | None, channel: str | None) -> dict:
        chosen = channel if channel in self.channels else self.default_channel()
        notify = (on == '1') if on in ('0', '1') else any(c.enabled for c in self.channels.values())
        return {'notify': notify and self.channels[chosen].enabled, 'channel': chosen, 'channels': [
            {'id': c.id, 'name': c.name, 'note': 'бот подключён' if c.enabled else 'не подключён: нужен токен бота и чат',
             **({} if c.enabled else {'off': True})} for c in self.channels.values()]}

    def case_queued(self, on: str | None, channel: str | None, case_id: str, reason: str, quote: dict | None):
        settings = self.view(on, channel)
        if settings['notify']:
            self.channels[settings['channel']].case_queued(case_id, reason, quote)
