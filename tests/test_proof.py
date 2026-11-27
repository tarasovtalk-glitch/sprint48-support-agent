"""Страница проверки для жюри: открывается без входа, итоги прогона и живые счётчики, без данных клиентов."""
from conftest import REQ
from eval.local import Chat, make_client
from support_app.proof import load_run


def test_proof_page_is_public_and_shows_run_and_live_numbers():
    client = make_client()
    chat = Chat(client)
    chat.say('Нужно КП на 19 бессрочных лицензий КриптоПро')
    chat.say(action='placement', value='workstation')
    chat.say(REQ)
    page = client.get('/support/api/proof')
    assert page.status_code == 200 and page.headers['content-type'].startswith('text/html')
    run = load_run()
    text = page.text
    assert f'{run["ok"]} из {run["auto"]}' in text and f'{run["strict"]} из {run["dialogues"]}' in text
    assert f'{run["attacks_ok"]} из {run["attacks"]}' in text and run['attacks_run'] in text
    assert 'Живые цифры этого стенда' in text and 'Обращений на стенде' in text
    for private in ('Вектор', '7701234560', '770101001', 'КриптоПро CSP'):
        assert private not in text
