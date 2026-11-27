import json

import pytest
from fastapi.testclient import TestClient

from eval.local import DEMO_KEY, MANAGER_KEY
from support_app.app import create_app, token_hash
from support_app.knowledge import save_answer
from support_app.store import Store


def test_cabinet_shows_jury_examples_and_hides_confirmed_test_cases(tmp_path, monkeypatch):
    database = tmp_path / 'support.sqlite3'
    jury_key = 'test-jury-key-0123456789abcdef'
    test_case = 'a' * 32
    real_case = 'b' * 32
    monkeypatch.setenv('SUPPORT_MANAGER_KEY', MANAGER_KEY)
    database.with_name('support-access-keys.json').write_text(json.dumps({token_hash(jury_key): 'jury'}), encoding='utf-8')
    database.with_name('hidden-test-cases.json').write_text(json.dumps([test_case]), encoding='utf-8')
    with Store(database).connect(write=True) as db:
        db.executemany('INSERT INTO cases(id,client_hash,offer,state) VALUES (?, ?, ?, ?)',
                       [(case, case, '{}', 'pending') for case in (test_case, real_case)])
        save_answer(db, real_case, 'Можно оплатить в рассрочку?', 'Для рассрочки нужна предоплата.')

    manager = {'X-Manager-Key': MANAGER_KEY}
    jury = {'X-Manager-Key': jury_key}
    prefix = '/support/api/manager'
    with TestClient(create_app(database)) as client:
        assert client.get(prefix + '/knowledge').status_code == 401
        assert [item['source_case'] for item in client.get(prefix + '/knowledge', headers=manager).json()['answers']] == [real_case]
        answers = client.get(prefix + '/knowledge', headers=jury).json()['answers']
        assert [item['source_case'] for item in answers] == ['jury-knowledge']
        assert answers[0]['question'] == 'Где закрывающие документы?'
        assert any(event['event'] == 'knowledge_saved' for event in client.get(prefix + '/cases/jury-knowledge/journal', headers=jury).json()['events'])
        assert client.get(prefix + '/cases/' + real_case + '/journal', headers=jury).status_code == 404
        for query in ('', '?state=all'):
            assert [case['id'] for case in client.get(prefix + '/cases' + query, headers=manager).json()['cases']] == [real_case]
        report = client.get(prefix + '/cases/export.csv', headers=manager).text
        assert real_case in report and test_case not in report
        empty_day = client.get(prefix + '/cases/export.csv?day=2020-01-01', headers=manager)
        assert empty_day.status_code == 200 and real_case not in empty_day.text
        assert 'cases-2020-01-01.csv' in empty_day.headers['content-disposition']
        assert client.get(prefix + '/cases/export.csv?day=bad', headers=manager).status_code == 422
        assert client.get(prefix + '/cases/' + test_case + '/journal', headers=manager).status_code == 200
        kb = client.get(prefix + '/knowledge', headers=manager).json()
        assert len(kb['agent_rules']) >= 3 and len(kb['articles']) >= 10
        metrics = client.get(prefix + '/metrics', headers=manager).json()
        assert metrics['cases'] == 1 and metrics['handed_to_manager'] == 1
        assert metrics['closed_by_agent'] == 0 and metrics['unfinished'] == 0
        assert metrics['total_limit_rub'] > 0 and isinstance(metrics['daily_cost_rub'], dict)
        jury_metrics = client.get(prefix + '/metrics', headers=jury).json()
        assert jury_metrics['sample'] is True and jury_metrics['cases'] == 2 and jury_metrics['handed_to_manager'] == 2
        assert client.get(prefix + '/agent/status', headers=manager).json()['state'] == 'on'
        assert client.post(prefix + '/agent/pause', headers=jury, json={'paused': True}).status_code == 403
        paused = client.post(prefix + '/agent/pause', headers=manager, json={'paused': True})
        assert paused.status_code == 200 and paused.json()['state'] == 'paused'
        assert client.get(prefix + '/agent/status', headers=manager).json()['state'] == 'paused'
        resumed = client.post(prefix + '/agent/pause', headers=manager, json={'paused': False})
        assert resumed.status_code == 200 and resumed.json()['state'] == 'on'


def test_jury_can_remember_answer_and_replay_without_affecting_other_keys(tmp_path, monkeypatch):
    database = tmp_path / 'support.sqlite3'
    keys = ['test-jury-1-0123456789abcdef', 'test-jury-2-0123456789abcdef']
    monkeypatch.setenv('SUPPORT_MANAGER_KEY', MANAGER_KEY)
    database.with_name('support-access-keys.json').write_text(json.dumps({token_hash(k): 'jury' for k in keys}), encoding='utf-8')
    question = 'Как получить копию закрывающих документов?'
    answer = 'Запросите дубликат документов через личный кабинет.'
    h1, h2 = [{'X-Manager-Key': key} for key in keys]
    admin = {'X-Manager-Key': MANAGER_KEY}
    prefix = '/support/api/manager'
    practice = prefix + '/jury/knowledge'
    payload = {'confirmed': True, 'question': question, 'answer': answer}
    with TestClient(create_app(database)) as client:
        assert client.post(practice, json=payload).status_code == 401
        assert client.post(practice, headers=admin, json=payload).status_code == 403
        remembered = client.post(practice, headers=h1, json=payload)
        assert remembered.status_code == 200 and remembered.json()['saved']
        result = client.post(practice + '/ask', headers=h1, json={'text': question}).json()
        assert result['remembered'] and answer in result['reply']
        assert result['case_id'] != remembered.json()['source_case']
        assert client.get(prefix + '/cases/' + result['case_id'] + '/journal', headers=h2).status_code == 404
        assert client.get(prefix + '/cases/' + result['case_id'] + '/journal', headers=admin).status_code == 404
        for headers in (h2, admin):
            assert all(a['answer'] != answer for a in client.get(prefix + '/knowledge', headers=headers).json()['answers'])


@pytest.mark.parametrize('chat_only', ['0', '1'])
def test_model_classification_receives_cues_in_both_modes(tmp_path, monkeypatch, chat_only):
    calls = []

    def classify(_store, _case_id, cue, **_options):
        calls.append(cue)
        return 'price'

    monkeypatch.setattr('support_app.app.classify', classify)
    monkeypatch.setenv('SUPPORT_DEMO_KEY', DEMO_KEY)
    monkeypatch.setenv('SUPPORT_CHAT_ONLY', chat_only)
    message = 'Нужно купить программу, цена? Меня зовут Иван Тестов, почта example@example.com, паспорт 1234 567890, ИНН 7701234560.'
    with TestClient(create_app(tmp_path / 'support.sqlite3')) as client:
        session = client.post('/support/api/sessions', headers={'X-Demo-Key': DEMO_KEY}).json()
        auth = {'Authorization': 'Bearer ' + session['session_token']}
        response = client.post('/support/api/case/messages', headers=auth, json={'text': message})
        assert response.status_code == 200
    assert calls == ['нужно купить программу цена']
