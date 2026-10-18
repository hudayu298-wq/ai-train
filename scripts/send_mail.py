"""Drain encrypted verification mail outbox. Run from systemd every minute."""
import os
import smtplib
import ssl
import sys
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import auth, database as d
from dotenv import load_dotenv
from sqlalchemy import select, update

load_dotenv(override=False)


def drain():
    if not auth.mail_ready():
        return
    for _ in range(20):
        with d.get_engine().begin() as conn:
            row = conn.execute(select(d.outbox).where(d.outbox.c.sent.is_(False),
                d.outbox.c.attempts < 3, d.outbox.c.available_at <= d.now())
                .with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not row:
                return
            payload = auth.decrypt(row['encrypted_message'])
            conn.execute(update(d.outbox).where(d.outbox.c.id == row['id']).values(
                attempts=row['attempts'] + 1, available_at=d.now() + timedelta(minutes=1)))
            try:
                msg = EmailMessage()
                msg['From'], msg['To'], msg['Subject'] = os.environ['SMTP_FROM'], payload['to'], payload['subject']
                msg.set_content(payload['body'])
                use_ssl = os.environ.get('SMTP_SSL', 'true').lower() == 'true'
                factory = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
                kwargs = {'context': ssl.create_default_context()} if use_ssl else {}
                with factory(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', '465' if use_ssl else '587')),
                             timeout=15, **kwargs) as server:
                    if not use_ssl:
                        server.starttls(context=ssl.create_default_context())
                    if os.environ.get('SMTP_USERNAME'):
                        server.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
                    server.send_message(msg)
                conn.execute(update(d.outbox).where(d.outbox.c.id == row['id']).values(sent=True, encrypted_message=''))
            except (OSError, smtplib.SMTPException):
                # Never print mail bodies, addresses, provider replies or credentials.
                print('Verification mail delivery failed; bounded retry scheduled.', file=sys.stderr)


if __name__ == '__main__':
    drain()
