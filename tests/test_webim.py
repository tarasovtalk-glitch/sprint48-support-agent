"""Адаптер Webim «Умный бот 2.0»: проверка на эмуляторе API Webim, без сети.

Форматы — по https://webim.ru/kb/bots/smart-bot/v-2-0.html: событие new_message, ответ {"result": "ok"},
send_message (operator / keyboard / file_operator), redirect_chat, заголовок Authorization: Token.
"""
import io
import json

import pytest

from conftest import REQ
from eval.local import make_client
from support_app.webim import WebimClient, button_id, parse_event

SECRET = 'webim-secret-0123456789abcdef'  # тестовое значение


class FakeWebim:
    """Эмулятор Webim API: принимает запросы бота и запоминает их."""

    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __call__(self, request, timeout):
        assert request.headers['Authorization'] == 'Token bot-token'
        self.calls.append((request.full_url.rsplit('/', 1)[1], json.loads(request.data)))

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response(json.dumps({'error': self.error} if self.error else {'result': 'ok'}).encode())

    def texts(self):
        return [b['message']['text'] for m, b in self.calls if m == 'send_message' and b['message']['kind'] == 'operator']

    def keyboards(self):
        return [b['message']['buttons'] for m, b in self.calls if m == 'send_message' and b['message']['kind'] == 'keyboard']


@pytest.fixture
def webim(monkeypatch):
    fake = FakeWebim()
    monkeypatch.setenv('WEBIM_BASE_URL', 'https://softline.webim.ru')
    monkeypatch.setenv('WEBIM_BOT_TOKEN', 'bot-token')
    monkeypatch.setenv('WEBIM_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('WEBIM_DEP_KEY', 'sales')
    monkeypatch.setenv('SUPPORT_PUBLIC_URL', 'https://analyzebot.ru')
    monkeypatch.setattr('support_app.webim.urlopen', fake, raising=False)
    original = WebimClient.__init__
    monkeypatch.setattr(WebimClient, '__init__', lambda self, base, token, opener=None: original(self, base, token, fake))
    monkeypatch.setattr('support_app.app.in_background', lambda function, *args: function(*args))
    client = make_client()
    return client, fake


def visitor(chat_id, mid, text):
    return {'event': 'new_message', 'chat_id': chat_id, 'message': {'id': mid, 'kind': 'visitor', 'text': text}}


def press(chat_id, mid, button):
    return {'event': 'new_message', 'chat_id': chat_id, 'message': {
        'id': mid, 'kind': 'keyboard_response',
        'data': {'button': {'id': button['id'], 'text': button['text']}, 'request': {'messageId': 'x'}}}}


def post(client, body, secret=SECRET):
    return client.post(f'/support/api/webim/{secret}', json=body)


def test_wrong_secret_or_disabled_is_not_found(webim):
    client, fake = webim
    assert post(client, visitor(1, 'm1', 'Здравствуйте'), secret='wrong-secret-0123456789abcdef').status_code == 404
    assert fake.calls == []


def test_dialogue_with_buttons_quote_file_and_handoff(webim):
    client, fake = webim
    r = post(client, visitor(77, 'm1', 'Нужно КП на 19 бессрочных лицензий КриптоПро'))
    assert r.status_code == 200 and r.json() == {'result': 'ok'}
    assert 'рабочие места или на сервер' in fake.texts()[-1]
    keyboard = fake.keyboards()[-1]
    workstation = next(row[0] for row in keyboard if 'рабоч' in row[0]['text'].lower())
    assert len(workstation['id']) <= 24 and workstation['id'].replace('-', '').replace('_', '').isalnum()

    post(client, press(77, 'm2', workstation))
    assert '70 300' in fake.texts()[-1]

    post(client, visitor(77, 'm3', REQ))
    assert 'Черновик КП' in fake.texts()[-1]
    redirects = [b for m, b in fake.calls if m == 'redirect_chat']
    assert redirects == [{'chat_id': 77, 'dep_key': 'sales'}]


def test_repeated_delivery_is_answered_once(webim):
    client, fake = webim
    post(client, visitor(5, 'same', 'Сколько стоит КриптоПро CSP 5.0?'))
    count = len(fake.calls)
    post(client, visitor(5, 'same', 'Сколько стоит КриптоПро CSP 5.0?'))
    assert len(fake.calls) == count


def test_chats_do_not_mix(webim):
    client, fake = webim
    post(client, visitor(1, 'a1', 'Нужно КП на 19 бессрочных лицензий КриптоПро'))
    post(client, visitor(2, 'b1', 'Здравствуйте'))
    chats = {b['chat_id'] for m, b in fake.calls}
    assert chats == {1, 2}
    manager = client.get('/support/api/manager/cases', headers={'X-Manager-Key': 'test-manager-key-0123456789abcdef'})
    assert manager.status_code == 200


def test_parse_ignores_files_and_service_messages():
    assert parse_event({'event': 'new_message', 'chat_id': 1, 'message': {'id': 'f', 'kind': 'file_visitor', 'data': {'state': 'upload'}}}) is None
    assert parse_event({'event': 'message_updated', 'chat_id': 1, 'message': {'id': 'x', 'kind': 'visitor', 'text': 'a'}}) is None
    assert parse_event({'event': 'new_chat', 'chat': {'id': 3}, 'messages': []}) is None
    assert parse_event({'event': 'new_chat', 'chat': {'id': 3}, 'messages': [{'id': 'q', 'kind': 'visitor', 'text': 'Привет'}]}) == (3, 'q', 'Привет', None)


def test_webim_error_in_body_counts_as_failure():
    client = WebimClient('https://softline.webim.ru', 'bot-token', FakeWebim(error='chat-not-found'))
    assert client.send_text(1, 'текст') is False
    assert WebimClient('http://insecure', 'bot-token').enabled is False
    assert button_id('select_offer', '410137') == button_id('select_offer', '410137') != button_id('select_offer', '410138')
