"""Operator-only account bootstrap / promotion. Passwords are entered interactively."""
import argparse
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
from sqlalchemy import select, update
from backend import auth, database as d

load_dotenv(override=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('create', help='Manually verified operator account; prompts for password')
    create.add_argument('--email', required=True)
    create.add_argument('--admin', action='store_true')
    promote = sub.add_parser('promote', help='Grant system catalog management to an existing user')
    promote.add_argument('--user-id', required=True)
    args = parser.parse_args()
    with d.get_engine().begin() as conn:
        if args.action == 'create':
            email = auth.EmailInput(email=args.email).email
            if conn.execute(select(d.users.c.id).where(d.users.c.email == email)).first():
                raise SystemExit('Account already exists; no changes made.')
            first = getpass('Password (15–128 characters): ')
            if not 15 <= len(first) <= 128 or getpass('Repeat password: ') != first:
                raise SystemExit('Password length or confirmation invalid; no changes made.')
            user = auth.new_user(conn, email, auth.passwords.hash(first), '运营者' if args.admin else '训练者')
            uid = user['id']
        else:
            uid = args.user_id
            if not conn.execute(select(d.users.c.id).where(d.users.c.id == uid, d.users.c.active.is_(True))).first():
                raise SystemExit('Active account not found; no changes made.')
        if args.action == 'promote' or args.admin:
            conn.execute(update(d.users).where(d.users.c.id == uid).values(role='admin'))
    print('Account operation completed; credentials were not printed.')


if __name__ == '__main__':
    main()
