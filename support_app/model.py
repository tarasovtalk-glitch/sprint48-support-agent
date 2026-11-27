import json
from datetime import datetime, timezone, timedelta
from urllib.error import URLError
from urllib.request import Request, urlopen

from .store import Store, append_event


SYSTEM = '''Определи намерение клиента магазина лицензий по списку разрешённых слов. Верни одно слово строчными буквами: price (цена, продление, сравнение), quote (КП), invoice (счёт), deferral (отсрочка), selection (подбор ПО), help (поддержка по заказу), handoff (менеджер), unknown (прочее). Не добавляй других слов.'''
INTENTS = {'price', 'quote', 'invoice', 'deferral', 'selection', 'help', 'handoff', 'unknown'}
INPUT_RATE = 100
OUTPUT_RATE = 200
MAX_OUTPUT = 72
QWEN_MODEL = 'qwen3.6-35b-a3b'
QWEN_RATE = (200, 300)  # ₽ за миллион токенов с НДС, без скидки за кеш и инструменты
MOSCOW = timezone(timedelta(hours=3))
TOOL_DESCRIPTIONS = {
    'clarify_requirements': 'Уточнить оставшиеся требования перед поиском лицензий.',
    'search_catalog': 'Получить варианты из каталога с учётом уже известных требований.',
    'check_registry': 'Проверить российский аналог или номер записи в реестре для подходящих вариантов.',
    'draft_quote': 'Подготовить черновик КП по выбранной позиции для проверки менеджером.',
    'contact_manager': 'Передать оператору запрос, который требует его решения.',
}


def completion(store: Store, case_id: str, body: dict, *, api_key: str, model_uri: str, daily: int, total: int):
    if not api_key or not model_uri:
        return None
    qwen = model_uri.rstrip('/').endswith('/' + QWEN_MODEL)
    input_rate, output_rate = QWEN_RATE if qwen else (INPUT_RATE, OUTPUT_RATE)
    day = datetime.now(MOSCOW).date().isoformat()
    reservation = store.reserve_model(case_id, day, 4096 * input_rate + MAX_OUTPUT * output_rate, daily, total)
    if reservation is None:
        return None

    body = json.dumps({
        'model': model_uri,
        'max_tokens': MAX_OUTPUT,
        'temperature': 0,
        **({'reasoning_effort': 'none'} if qwen else {}),
        **body,
    }).encode()
    request = Request('https://ai.api.cloud.yandex.net/v1/chat/completions', data=body, headers={
        'Authorization': 'Api-Key ' + api_key,
        'Content-Type': 'application/json',
    })
    try:
        with urlopen(request, timeout=12) as response:
            result = json.load(response)
        usage = result['usage']
        input_tokens = max(0, int(usage['prompt_tokens']))
        output_tokens = max(0, int(usage['completion_tokens']))
        message = result['choices'][0]['message']
    except (URLError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        # On an uncertain failure the provider may still have charged for the request.
        with store.connect(write=True) as db:
            append_event(db, case_id, 'model_unavailable')
        return None
    store.record_model(reservation, input_tokens, output_tokens, input_tokens * input_rate + output_tokens * output_rate)
    return message if isinstance(message, dict) else None


def classify(store: Store, case_id: str, text: str, **options) -> str:
    message = completion(store, case_id, {
        'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}],
    }, **options)
    content = (message or {}).get('content')
    intent = content.strip().lower() if isinstance(content, str) else 'unknown'
    return intent if intent in INTENTS else 'unknown'


def choose_tool(store: Store, case_id: str, cue: str, available: tuple[str, ...], **options) -> str | None:
    tools = [
        {'type': 'function', 'function': {'name': name, 'description': TOOL_DESCRIPTIONS[name],
         'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}
        for name in available
    ]
    message = completion(store, case_id, {
        'messages': [
            {'role': 'system', 'content': 'Выбери и вызови ровно один подходящий инструмент магазина. Не выдумывай данные и не пиши обычный текст.'},
            {'role': 'user', 'content': cue},
        ],
        'tools': tools,
        'tool_choice': 'auto',
    }, **options)
    calls = (message or {}).get('tool_calls') or []
    if not isinstance(calls, list) or len(calls) != 1:
        return None
    try:
        function = calls[0]['function']
        name = function['name']
        args = json.loads(function.get('arguments') or '{}')
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return name if name in available and args == {} else None
