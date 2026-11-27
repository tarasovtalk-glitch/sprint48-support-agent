import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.local import Chat, make_client  # noqa: E402

REQ = 'ООО «Вектор», ИНН 7701234560, КПП 770101001'  # выдуманные тестовые реквизиты


@pytest.fixture(scope='session')
def client():
    return make_client()


@pytest.fixture
def chat(client):
    return Chat(client)
