"""Уведомление менеджеру в Telegram: включается переменными, без персональных данных, сбой не ломает чат."""
import io
import json

from conftest import REQ
from eval.local import Chat, make_client
from support_app.notify import Telegram, notice_text

QUOTE = {'amount_kopecks': 7030000, 'items': [{'id': '410137', 'quantity': 19}],
         'customer': 'ООО «Вектор»', 'inn': '7701234560', 'kpp': '770101001', 'email': 'buyer@example.com'}


def test_notice_has_reason_amount_and_link_but_no_customer_data():
    text = notice_text('0123456789abcdef', 'quote_review', QUOTE, 'https://analyzebot.ru/support/cabinet/')
    assert 'Черновик КП на проверку' in text and '70 300' in text and '1 поз.' in text
    assert 'https://analyzebot.ru/support/cabinet/#queue' in text and '01234567' in text
    for private in ('Вектор', '7701234560', '770101001', 'example.com'):
        assert private not in text


def test_disabled_without_token_or_chat():
    sent = []
    assert not Telegram('', '123').enabled and not Telegram('token', '').enabled
    assert Telegram('', '', opener=lambda *a, **k: sent.append(a)).case_queued('id', 'tender', None, background=False) is None
    assert sent == []


def test_delivery_posts_to_bot_api_and_survives_failure():
    requests = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout):
        requests.append(request)
        return Response(b'{"ok": true}')

    bot = Telegram('123:abc', '-100500', opener=opener)
    assert bot.case_queued('caseid', 'tender', None, background=False) is True
    assert requests[0].full_url == 'https://api.telegram.org/bot123:abc/sendMessage'
    body = json.loads(requests[0].data)
    assert body['chat_id'] == '-100500' and 'Тендер или госзакупка' in body['text']

    def broken(request, timeout):
        raise OSError('network down')

    assert Telegram('123:abc', '-100500', opener=broken).case_queued('caseid', 'tender', None, background=False) is False


def test_chat_handoff_sends_one_notice(monkeypatch):
    sent = []
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123:abc')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '-100500')
    monkeypatch.setattr(Telegram, 'deliver', lambda self, text: sent.append(text) or True)
    monkeypatch.setattr('support_app.notify.in_background', lambda function, *args: function(*args))
    chat = Chat(make_client())
    chat.say('Нужно КП на 19 бессрочных лицензий КриптоПро')
    chat.say(action='placement', value='workstation')
    reply = chat.say(REQ)
    assert reply['case']['state'] == 'pending'
    assert len(sent) == 1 and 'Черновик КП' in sent[0] and '70 300' in sent[0]
    assert '7701234560' not in sent[0] and 'Вектор' not in sent[0]
    chat.say('Когда ответит менеджер?')  # обращение уже в очереди — второго уведомления нет
    assert len(sent) == 1
