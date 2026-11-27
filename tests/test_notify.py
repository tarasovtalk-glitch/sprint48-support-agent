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


# --- MAX и выбор канала в кабинете ---
import json as _json  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from eval.local import MANAGER_KEY  # noqa: E402
from support_app.app import create_app, token_hash  # noqa: E402
from support_app.notify import Max, Notifier  # noqa: E402

MGR = {'X-Manager-Key': 'test-manager-key-0123456789abcdef'}


def test_max_posts_to_platform_api_with_header_token():
    requests = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout):
        requests.append(request)
        return Response(b'{"message": {"body": {"mid": "m1"}}}')

    bot = Max('max-token', '-7001', opener=opener)
    assert bot.case_queued('caseid', 'tender', None, background=False) is True
    sent = requests[0]
    assert sent.full_url == 'https://platform-api2.max.ru/messages?chat_id=-7001&disable_link_preview=true'
    assert sent.headers['Authorization'] == 'max-token' and 'access_token' not in sent.full_url
    assert 'Тендер или госзакупка' in json.loads(sent.data)['text']

    def error(request, timeout):
        return Response(b'{"code": "chat.denied", "message": "denied"}')

    assert Max('max-token', '-7001', opener=error).case_queued('caseid', 'tender', None, background=False) is False


def test_notifier_defaults_and_choice():
    tg, mx = Telegram('t', '1'), Max('', '')
    view = Notifier(tg, mx).view(None, None)
    assert view['notify'] is True and view['channel'] == 'telegram'
    assert [c.get('off', False) for c in view['channels']] == [False, True]
    assert Notifier(tg, mx).view('0', None)['notify'] is False
    assert Notifier(Telegram('', ''), Max('', '')).view(None, None)['notify'] is False  # ни один бот не подключён


def chat_to_queue(client):
    chat = Chat(client)
    chat.say('Нужно КП на 19 бессрочных лицензий КриптоПро')
    chat.say(action='placement', value='workstation')
    assert chat.say(REQ)['case']['state'] == 'pending'


def test_manager_switches_channel_and_turns_notifications_off(monkeypatch):
    sent = []
    for name, value in (('TELEGRAM_BOT_TOKEN', '123:abc'), ('TELEGRAM_CHAT_ID', '-100500'),
                        ('MAX_BOT_TOKEN', 'max-token'), ('MAX_CHAT_ID', '-7001')):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(Telegram, 'deliver', lambda self, text: sent.append(('telegram', text)) or True)
    monkeypatch.setattr(Max, 'deliver', lambda self, text: sent.append(('max', text)) or True)
    monkeypatch.setattr('support_app.notify.in_background', lambda function, *args: function(*args))
    client = make_client()
    url = '/support/api/manager/notifications'
    view = client.get(url, headers=MGR).json()
    assert view['notify'] is True and view['channel'] == 'telegram' and view['editable'] is True

    assert client.post(url, headers=MGR, json={'channel': 'max'}).json()['channel'] == 'max'
    chat_to_queue(client)
    assert [c for c, _ in sent] == ['max']

    assert client.post(url, headers=MGR, json={'notify': False}).json()['notify'] is False
    chat_to_queue(client)
    assert len(sent) == 1  # выключено — ни в один канал

    assert client.post(url, headers=MGR, json={'channel': 'whatsapp'}).status_code == 422
    assert client.post(url, json={'notify': True}).status_code in (401, 403)


def test_unconnected_channel_cannot_be_chosen_and_jury_cannot_change(tmp_path, monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123:abc')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '-100500')
    monkeypatch.setenv('SUPPORT_MANAGER_KEY', MANAGER_KEY)
    database = tmp_path / 'support.sqlite3'
    jury_key = 'test-jury-key-0123456789abcdef'
    database.with_name('support-access-keys.json').write_text(_json.dumps({token_hash(jury_key): 'jury'}), encoding='utf-8')
    with TestClient(create_app(database)) as client:
        url = '/support/api/manager/notifications'
        assert client.post(url, headers={'X-Manager-Key': MANAGER_KEY}, json={'channel': 'max'}).status_code == 409
        jury = {'X-Manager-Key': jury_key}
        assert client.get(url, headers=jury).json()['editable'] is False
        assert client.post(url, headers=jury, json={'notify': False}).status_code in (401, 403)
