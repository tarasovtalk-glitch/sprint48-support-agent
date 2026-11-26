import json
from email.message import EmailMessage
from pathlib import Path
from smtplib import SMTP, SMTPException
from threading import Event
from time import time

from .documents import render_pdf, rubles
from .store import Store, append_event


def send_job(host: str, port: int, font: Path, job):
    offer = json.loads(job['offer'])
    message = EmailMessage()
    message['From'] = 'agent@softline-demo.test'
    message['Message-ID'] = f'<{job["id"]}@softline-demo.test>'
    if job['kind'] == 'handoff':
        message['To'] = 'manager@softline-demo.test'
        message['Subject'] = 'Демо: требуется решение менеджера'
        message.set_content(f'Отсрочка на {offer["requested_days"]} дней. Сумма {rubles(offer["renewal_total_kopecks"])} Обращение {job["case_id"]}.')
    else:
        message['To'] = 'olga@softline-demo.test'
        message['Subject'] = 'Демо: отсрочка согласована'
        message.set_content(f'Оплатить до {offer["payment_due"]}. Демонстрационный код: SMF-DEMO-KEY-NOT-FOR-ACTIVATION.')
        message.add_attachment(render_pdf('invoice', offer, font), maintype='application', subtype='pdf', filename='invoice.pdf')
    with SMTP(host, port, timeout=5) as smtp:
        smtp.send_message(message)


def next_job(store: Store):
    now = int(time())
    with store.connect(write=True) as db:
        row = db.execute('''
            SELECT * FROM mail_outbox WHERE sent_at IS NULL AND attempts < 3 AND next_attempt_at <= ? ORDER BY rowid LIMIT 1
        ''', (now,)).fetchone()
        if row:
            db.execute('UPDATE mail_outbox SET attempts=attempts+1,next_attempt_at=? WHERE id=?', (now + 30, row['id']))
        return row


def run_mail_queue(store: Store, host: str, port: int, font: Path, stop: Event):
    while not stop.is_set():
        job = next_job(store)
        if job is None:
            stop.wait(2)
            continue
        try:
            send_job(host, port, font, job)
        except (SMTPException, OSError):
            if job['attempts'] == 2:
                with store.connect(write=True) as db:
                    append_event(db, job['case_id'], 'demo_email_failed', job['kind'])
            continue
        with store.connect(write=True) as db:
            db.execute('UPDATE mail_outbox SET sent_at=? WHERE id=?', (int(time()), job['id']))
            append_event(db, job['case_id'], 'demo_email_delivered', job['kind'])
