#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y postgresql postgresql-client
python3 - <<'PY'
import os
from pathlib import Path
import secrets
import subprocess

root = Path('/etc/liftlab')
root.mkdir(mode=0o700, exist_ok=True)
env_file = root / 'liftlab.env'
current = env_file.read_text() if env_file.exists() else ''
values = dict(line.split('=', 1) for line in current.splitlines() if '=' in line and not line.startswith('#'))
if values.get('DATABASE_URL'):
    assert values['DATABASE_URL'].startswith('postgresql+psycopg://liftlab_app@') or values['DATABASE_URL'].startswith('postgresql+psycopg://liftlab_app:'), 'Unexpected configured database; review manually'
    print('PostgreSQL environment already configured; credentials were preserved.')
    raise SystemExit(0)

def sql(statement):
    result = subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-At'],
        input=statement, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('PostgreSQL provisioning failed; inspect the local database state without printing credentials.')
    return result.stdout.strip()

assert not sql("SELECT 1 FROM pg_database WHERE datname='liftlab';"), 'Existing liftlab database requires explicit review'
assert not sql("SELECT 1 FROM pg_roles WHERE rolname IN ('liftlab_owner','liftlab_app');"), 'Existing LiftLab roles require explicit review'
app_password, owner_password = secrets.token_hex(32), secrets.token_hex(32)
sql(f"CREATE ROLE liftlab_owner LOGIN PASSWORD '{owner_password}'; CREATE ROLE liftlab_app LOGIN PASSWORD '{app_password}';")
sql('CREATE DATABASE liftlab OWNER liftlab_owner;')
sql("ALTER SYSTEM SET listen_addresses='localhost';")
sql("ALTER SYSTEM SET max_connections='40';")
sql("ALTER SYSTEM SET shared_buffers='128MB';")
values.update(DATABASE_URL=f'postgresql+psycopg://liftlab_app:{app_password}@127.0.0.1:5432/liftlab',
    AUTH_SECRET=secrets.token_urlsafe(48), AUTH_INVITE_CODE=secrets.token_urlsafe(24),
    REGISTRATION_OPEN='false', APP_ENV='production')
for key in ('WECHAT_APP_ID', 'WECHAT_APP_SECRET', 'SMTP_HOST', 'SMTP_FROM', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'APP_SUPPORT_EMAIL'):
    values.setdefault(key, '')
def write_private(path, content):
    tmp = path.with_suffix('.next')
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
write_private(env_file, '\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
write_private(root / 'migration.env', f'DATABASE_URL=postgresql+psycopg://liftlab_owner:{owner_password}@127.0.0.1:5432/liftlab\n')
subprocess.run(['systemctl', 'restart', 'postgresql'], check=True)
print('Provisioned loopback PostgreSQL, separate owner/application roles and private environment files. No credentials displayed.')
PY
