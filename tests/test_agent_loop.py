"""Многошаговый ход агента: модель выбирает инструмент, читающий инструмент выполняется, итог возвращается модели.

Модель подменяется: сеть не нужна, проверяем протокол цикла, границы и что в модель не уходят цены и данные клиента.
"""
import json

import pytest

from eval.local import MANAGER_KEY, Chat, make_client
from support_app import model


def call(name, args='{}', ident='c1'):
    return {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': args}}]}


class FakeModel:
    """Отвечает заранее заданными вызовами инструментов и запоминает, что получила модель."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen = []

    def __call__(self, _store, _case_id, body, **_options):
        self.seen.append(body)
        if 'tools' not in body:  # classify: намерение
            return {'role': 'assistant', 'content': 'unknown'}
        return self.answers.pop(0) if self.answers else None


@pytest.fixture
def fake(monkeypatch):
    def install(*answers):
        f = FakeModel(*answers)
        monkeypatch.setattr(model, 'completion', f)
        return f
    return install


def test_observation_goes_back_to_model_and_next_step_follows(fake):
    f = fake(call('search_catalog'), call('check_registry', ident='c2'), call('answer_customer', ident='c3'))
    seen = []
    steps = model.run_agent(None, 'case', 'Клиент спрашивает про реестр.', ('check_registry', 'search_catalog'),
                            lambda name: seen.append(name) or f'итог {name}')
    assert steps == ['search_catalog', 'check_registry']
    assert seen == ['search_catalog', 'check_registry']
    tool_messages = [m for m in f.seen[-1]['messages'] if m['role'] == 'tool']
    assert [m['content'] for m in tool_messages] == ['итог search_catalog', 'итог check_registry']
    assert [m['tool_call_id'] for m in tool_messages] == ['c1', 'c2']


def test_empty_catalog_result_lets_model_call_manager(fake):
    f = fake(call('search_catalog'), call('contact_manager', ident='c2'))
    steps = model.run_agent(None, 'case', 'cue', ('search_catalog', 'clarify_requirements'),
                            lambda name: 'Подходящих вариантов нет в каталоге.')
    assert steps == ['search_catalog', 'contact_manager']
    offered = [t['function']['name'] for t in f.seen[1]['tools']]
    assert 'contact_manager' in offered and 'answer_customer' in offered


def test_manager_is_not_offered_when_catalog_has_options(fake):
    f = fake(call('search_catalog'), call('contact_manager', ident='c2'))
    steps = model.run_agent(None, 'case', 'cue', ('search_catalog', 'clarify_requirements'),
                            lambda name: 'Найдено групп вариантов: 2.')
    assert steps == ['search_catalog']  # неразрешённый инструмент останавливает цикл, решает путь по правилам
    assert 'contact_manager' not in [t['function']['name'] for t in f.seen[1]['tools']]


@pytest.mark.parametrize('answer', [
    None,                                            # модель недоступна
    {'role': 'assistant', 'content': 'текст'},       # обычный текст вместо инструмента
    call('search_catalog', args='{"price": 1}'),     # модель пытается передать данные
    call('draft_invoice'),                           # инструмента нет в списке
    call('answer_customer'),                         # сразу закончить — работают правила
])
def test_invalid_first_answer_falls_back_to_rules(fake, answer):
    fake(answer)
    assert model.run_agent(None, 'case', 'cue', ('search_catalog',), lambda name: 'итог') == []


def test_action_tool_ends_the_loop_and_repeats_stop_it(fake):
    fake(call('clarify_requirements'), call('search_catalog'))
    assert model.run_agent(None, 'case', 'cue', ('clarify_requirements', 'search_catalog'), lambda n: 'итог') == ['clarify_requirements']
    fake(call('search_catalog'), call('search_catalog', ident='c2'))
    assert model.run_agent(None, 'case', 'cue', ('search_catalog',), lambda n: 'итог') == ['search_catalog']


def test_loop_is_bounded(fake):
    f = fake(*[call('search_catalog', ident=f'c{i}') for i in range(10)])
    model.run_agent(None, 'case', 'cue', ('search_catalog', 'check_registry'), lambda n: 'итог')
    assert len([b for b in f.seen if 'tools' in b]) <= model.AGENT_MAX_STEPS


def journal(client, case_id):
    r = client.get(f'/support/api/manager/cases/{case_id}/journal', headers={'X-Manager-Key': MANAGER_KEY})
    assert r.status_code == 200, r.text
    return r.json()


def test_chat_runs_several_model_steps_and_journal_shows_them(fake):
    client = make_client()
    chat = Chat(client)
    chat.say('Нужно защитить почту и файлы на 50 сотрудников')
    chat.say(action='focus', value='all')
    chat.say(action='term', value='12')
    f = fake(call('search_catalog'), call('answer_customer', ident='c2'))
    r = chat.say(action='deployment', value='local')
    assert 'Варианты по данным каталога' in r['reply'] and '₽' in r['reply']
    bodies = [b for b in f.seen if 'tools' in b]
    assert len(bodies) == 2
    observation = next(m for m in bodies[1]['messages'] if m['role'] == 'tool')['content']
    assert observation.startswith('Найдено групп вариантов')
    sent = json.dumps(bodies, ensure_ascii=False)
    assert '₽' not in sent and 'http' not in sent and '50' not in sent
    events = [(e['event'], e['detail']) for e in journal(client, r['case']['id'])['events']]
    assert ('model_tool_selected', 'search_catalog') in events
    assert ('model_tool_executed', 'search_catalog') in events


def test_registry_question_runs_search_then_registry(fake):
    client = make_client()
    chat = Chat(client)
    chat.say('Не знаю, что нужно, но хотим защитить почту и файлы на 50 сотрудников')
    chat.say('Почта на своем сервере Linux, компьютеры Windows')
    f = fake(call('search_catalog'), call('check_registry', ident='c2'), call('answer_customer', ident='c3'))
    r = chat.say('А российский аналог?')
    assert 'реестр' in r['reply'].lower()
    bodies = [b for b in f.seen if 'tools' in b]
    observations = [m['content'] for m in bodies[-1]['messages'] if m['role'] == 'tool']
    assert len(observations) == 2 and observations[1].startswith('С записью в реестре')
    assert 'ИНН' not in json.dumps(bodies, ensure_ascii=False)
    events = [(e['event'], e['detail']) for e in journal(client, r['case']['id'])['events']]
    assert ('model_tool_selected', 'search_catalog → check_registry') in events
    executed = [d for e, d in events if e == 'model_tool_executed']
    assert executed[:2] == ['search_catalog', 'check_registry']
