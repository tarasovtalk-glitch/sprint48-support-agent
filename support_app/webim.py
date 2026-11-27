"""Адаптер Webim «Умный бот 2.0» (External Bot API 2.0): тот же агент в чате сайта store.softline.ru.

Схема Webim асинхронная (https://webim.ru/kb/bots/smart-bot/v-2-0.html):
- Webim шлёт событие POST на адрес бота; бот сразу отвечает 200 и {"result": "ok"}, иначе чат уходит в общую очередь;
- ответ клиенту бот отправляет отдельным запросом: POST https://{аккаунт}.webim.ru/api/bot/v2/send_message,
  заголовок Authorization: Token {токен бота};
- передача человеку — POST /api/bot/v2/redirect_chat с dep_key отдела (или без него — в общую очередь).
Входящие запросы Webim не подписывает, поэтому адрес бота содержит секрет: /support/api/webim/{секрет}.
Webim повторяет недоставленные события до 5 раз — повтор message.id обрабатываем один раз.
"""
import hashlib
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

BUTTON_ID_LENGTH = 20  # Webim: латиница, цифры, - и _, не длиннее 24 знаков


def button_id(action: str, value: str) -> str:
    return 'b' + hashlib.sha256(f'{action}:{value}'.encode()).hexdigest()[:BUTTON_ID_LENGTH - 1]


def parse_event(body: dict):
    """Событие Webim → (chat_id, message_id, текст, id нажатой кнопки) или None, если отвечать не нужно."""
    if not isinstance(body, dict):
        return None
    event = body.get('event')
    if event == 'new_chat':
        chat = body.get('chat') or {}
        visitor = [m for m in body.get('messages') or [] if isinstance(m, dict) and m.get('kind') == 'visitor' and m.get('text')]
        if not isinstance(chat.get('id'), int) or not visitor:
            return None
        last = visitor[-1]
        return chat['id'], str(last.get('id') or ''), str(last['text']), None
    if event != 'new_message' or not isinstance(body.get('chat_id'), int):
        return None
    message = body.get('message') or {}
    kind, mid = message.get('kind'), str(message.get('id') or '')
    if kind == 'visitor' and isinstance(message.get('text'), str) and message['text'].strip():
        return body['chat_id'], mid, message['text'], None
    if kind == 'keyboard_response':
        button = ((message.get('data') or {}).get('button') or {})
        if isinstance(button.get('id'), str):
            return body['chat_id'], mid, str(button.get('text') or ''), button['id']
    return None  # файлы, служебные сообщения и обновления — менеджер увидит их в Webim сам


class WebimClient:
    def __init__(self, base_url: str, token: str, opener=urlopen):
        self.base_url, self.token, self.opener = base_url.rstrip('/'), token.strip(), opener

    @property
    def enabled(self) -> bool:
        return self.base_url.startswith('https://') and bool(self.token)

    def call(self, method: str, body: dict) -> bool:
        request = Request(f'{self.base_url}/api/bot/v2/{method}', data=json.dumps(body, ensure_ascii=False).encode(),
                          headers={'Authorization': 'Token ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener(request, timeout=10) as response:
                raw = response.read()
            answer = json.loads(raw) if raw else {}
        except (URLError, OSError, ValueError, AttributeError):
            return False
        return not (isinstance(answer, dict) and answer.get('error'))  # Webim шлёт ошибки и с кодом 200

    def send_text(self, chat_id: int, text: str) -> bool:
        return self.call('send_message', {'chat_id': chat_id, 'message': {'kind': 'operator', 'text': text}})

    def send_buttons(self, chat_id: int, items: list[dict]) -> bool:
        rows = [[{'id': button_id(b['action'], b['value']), 'text': b['label'][:64]}] for b in items]
        return self.call('send_message', {'chat_id': chat_id, 'message': {'kind': 'keyboard', 'buttons': rows}})

    def send_file(self, chat_id: int, url: str, name: str) -> bool:
        return self.call('send_message', {'chat_id': chat_id, 'message': {
            'kind': 'file_operator', 'data': {'url': url, 'name': name, 'media_type': 'application/pdf'}}})

    def redirect(self, chat_id: int, dep_key: str = '') -> bool:
        return self.call('redirect_chat', {'chat_id': chat_id, **({'dep_key': dep_key} if dep_key else {})})
