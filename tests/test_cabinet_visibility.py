import json

from fastapi.testclient import TestClient

from eval.local import MANAGER_KEY
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
        assert client.get(prefix + '/cases/' + test_case + '/journal', headers=manager).status_code == 200
        kb = client.get(prefix + '/knowledge', headers=manager).json()
        assert len(kb['agent_rules']) >= 3 and len(kb['articles']) >= 10
        metrics = client.get(prefix + '/metrics', headers=manager).json()
        assert metrics['cases'] == 1 and metrics['handed_to_manager'] == 1
        assert metrics['closed_by_agent'] == 0 and metrics['unfinished'] == 0
        assert metrics['total_limit_rub'] > 0 and isinstance(metrics['daily_cost_rub'], dict)
        jury_metrics = client.get(prefix + '/metrics', headers=jury).json()
        assert jury_metrics['sample'] is True and jury_metrics['cases'] == 2 and jury_metrics['handed_to_manager'] == 2
