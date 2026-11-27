from pathlib import Path

from .knowledge import save_answer
from .store import Store, append_event, save_chat_message, save_chat_state


def create_jury_store(path: Path) -> Store:
    store = Store(path)
    with store.connect(write=True) as db:
        case = 'jury-catalog'
        db.execute('INSERT INTO cases(id,client_hash,offer,state) VALUES (?,?,?,?)',
                   (case, case, '{}', 'approved'))
        append_event(db, case, 'opened', 'Тестовый диалог для жюри')
        save_chat_message(db, case, 'client', 'Нужно КП на 19 бессрочных лицензий КриптоПро.')
        save_chat_message(db, case, 'agent', 'Лицензии нужны на рабочие места или на сервер?')
        save_chat_message(db, case, 'client', 'На рабочие места. ООО «Демо», ИНН 0000000000, КПП 000000000.')
        save_chat_message(db, case, 'agent', '19 рабочих мест по 3 700 ₽ — 70 300 ₽. Передал КП на проверку.')
        append_event(db, case, 'quote_amount_calculated', '7030000')
        append_event(db, case, 'sent_to_manager', 'quote_review')
        save_chat_state(db, case, {'queue_reason': 'quote_review', 'quote': {
            'offer': {'name': 'КриптоПро CSP 5.0', 'id': '410137'},
            'customer': 'ООО «Демо»', 'inn': '0000000000', 'kpp': '000000000',
            'quantity': 19, 'amount_kopecks': 7_030_000, 'payment_terms': 'Предоплата по оферте',
        }})
        save_chat_message(db, case, 'manager', 'Коммерческое предложение согласовано в тестовом сценарии.')
        append_event(db, case, 'manager_decision', 'approved')

        case = 'jury-knowledge'
        db.execute('INSERT INTO cases(id,client_hash,offer,state) VALUES (?,?,?,?)',
                   (case, case, '{}', 'approved'))
        append_event(db, case, 'opened', 'Тестовый диалог для жюри')
        question = 'Где закрывающие документы?'
        answer = ('Закрывающие документы по заказу проверяйте в личном кабинете Store. '
                  'Порядок отправки документов и ЭДО описан в справке: https://store.softline.ru/delivery_info/#q7')
        save_chat_message(db, case, 'client', question)
        save_chat_message(db, case, 'agent', 'Передал вопрос менеджеру.')
        append_event(db, case, 'sent_to_manager', 'closing_documents')
        save_chat_message(db, case, 'manager', answer)
        append_event(db, case, 'manager_decision', 'approved')
        entry = save_answer(db, case, question, answer)
        append_event(db, case, 'knowledge_saved', str(entry['id']))
        save_chat_state(db, case, {'queue_reason': 'closing_documents'})
    return store
