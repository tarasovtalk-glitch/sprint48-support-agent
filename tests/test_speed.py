"""Скорость в кабинете — живой замер стенда, а не заданные числа."""
import uuid

from conftest import REQ
from eval.local import Chat, make_client
from support_app.app import median

MANAGER = {'X-Manager-Key': 'test-manager-key-0123456789abcdef'}


def metrics(client):
    response = client.get('/support/api/manager/metrics', headers=MANAGER)
    assert response.status_code == 200
    return response.json()


def test_median():
    assert median([]) is None
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5


def test_no_replies_yet_means_no_numbers():
    data = metrics(make_client())
    assert data['agent_reply_median_ms'] is None and data['agent_replies'] == 0
    assert data['manager_reply_median_s'] is None and data['manager_replies'] == 0


def test_agent_and_manager_speed_are_measured():
    client = make_client()
    chat = Chat(client)
    chat.say('Нужно КП на 19 бессрочных лицензий КриптоПро')
    chat.say(action='placement', value='workstation')
    reply = chat.say(REQ)
    assert reply['case']['state'] == 'pending'
    data = metrics(client)
    assert data['agent_replies'] == 3 and 0 <= data['agent_reply_median_ms'] < 10_000
    assert data['manager_replies'] == 0  # менеджер ещё не ответил

    case_id = reply['case']['id']
    decided = client.post(f'/support/api/manager/cases/{case_id}/decision', headers=MANAGER,
                          json={'choice': 'approve', 'version': reply['case']['version'],
                                'request_id': str(uuid.uuid4()), 'note': ''})
    assert decided.status_code == 200, decided.text
    data = metrics(client)
    assert data['manager_replies'] == 1 and data['manager_reply_median_s'] >= 0
