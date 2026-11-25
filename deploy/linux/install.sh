#!/usr/bin/env bash
# Install an isolated release. All application traffic stays on loopback.
set -euo pipefail
umask 027

if [[ "$(id -u)" != 0 ]]; then
  echo 'Run this installer as root or using sudo.' >&2
  exit 1
fi
source_dir="$(realpath "${1:?Usage: install.sh SOURCE_DIRECTORY RELEASE_ID}")"
release_id="${2:?Missing release ID}"
if [[ ! "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,90}$ ]]; then
  echo 'Invalid release ID.' >&2
  exit 1
fi
for file in backend/app.py backend/requirements.lock.txt preview/index.html .env.example RELEASE.json scripts/backup_data.py; do
  [[ -f "$source_dir/$file" ]] || { echo "Missing package file: $file" >&2; exit 1; }
done
for tool in python3 systemctl useradd install runuser; do
  command -v "$tool" >/dev/null || { echo "Install prerequisite: $tool" >&2; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
python3 - "$source_dir" "$release_id" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
manifest = json.loads((root / 'RELEASE.json').read_text(encoding='utf-8'))
assert manifest['release'] == sys.argv[2], 'Package release ID mismatch'
for name, expected in manifest['files'].items():
    rel = Path(name)
    assert not rel.is_absolute() and '..' not in rel.parts, 'Invalid manifest path'
    path = root / rel
    assert path.resolve().is_relative_to(root) and not path.is_symlink(), 'Invalid package entry'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'Checksum mismatch: {name}'
print('Verified package source checksums.')
PY

base=/opt/liftlab
release_dir="$base/releases/$release_id"
data_dir=/var/lib/liftlab
backup_dir=/var/backups/liftlab
env_dir=/etc/liftlab
if [[ -e "$release_dir" ]]; then
  echo 'Release already exists; build a new package rather than overwriting it.' >&2
  exit 1
fi
if [[ -e "$base/current" && ! -L "$base/current" ]]; then
  echo '/opt/liftlab/current must be an installer-managed symlink.' >&2
  exit 1
fi
id liftlab >/dev/null 2>&1 || useradd --system --home-dir /var/lib/liftlab --shell /usr/sbin/nologin liftlab
install -d -m 0755 "$base" "$base/releases" "$release_dir"
install -d -m 0700 "$env_dir"
install -d -m 0700 -o liftlab -g liftlab "$data_dir" "$backup_dir"
cp -a "$source_dir/backend" "$source_dir/preview" "$release_dir/"
install -d -m 0755 "$release_dir/scripts"
install -m 0644 "$source_dir/scripts/backup_data.py" "$release_dir/scripts/backup_data.py"
install -m 0644 "$source_dir/scripts/send_mail.py" "$release_dir/scripts/send_mail.py"
install -m 0644 "$source_dir/scripts/manage_account.py" "$release_dir/scripts/manage_account.py"
install -m 0644 "$source_dir/scripts/agent_worker.py" "$release_dir/scripts/agent_worker.py"
install -m 0644 "$source_dir/scripts/download_retrieval_models.py" "$release_dir/scripts/download_retrieval_models.py"
install -m 0644 "$source_dir/alembic.ini" "$release_dir/alembic.ini"
install -m 0644 "$source_dir/RELEASE.json" "$release_dir/RELEASE.json"
if [[ ! -f "$env_dir/liftlab.env" ]]; then
  install -m 0600 "$source_dir/.env.example" "$env_dir/liftlab.env"
fi
# Keep existing model credentials. Configure new credentials separately via SSH.
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install --disable-pip-version-check -r "$release_dir/backend/requirements.lock.txt"
"$release_dir/.venv/bin/python" -m pip check
# Source and virtualenv are root-owned and readable by the service group.
chown -hR root:liftlab "$release_dir"
chmod -R u=rwX,g=rX,o= "$release_dir"

previous="$(readlink -f "$base/current" 2>/dev/null || true)"
systemctl stop liftlab-agent.timer liftlab-agent.service 2>/dev/null || true
was_active=0
systemctl is-active --quiet liftlab.service && was_active=1
# Take a stable pre-deployment snapshot with the writer stopped.
account_release=0
if "$release_dir/.venv/bin/python" -c 'import json,urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health",timeout=2))["mode"]=="multi_user"' >/dev/null 2>&1; then
  account_release=1
fi
if [[ "$account_release" == 1 ]]; then
  systemctl stop liftlab.service
  if ! systemctl start liftlab-backup.service; then
    if [[ "$was_active" == 1 ]]; then systemctl start liftlab.service; fi
    echo 'PostgreSQL backup failed; deployment stopped.' >&2
    exit 1
  fi
fi
if [[ -f "$data_dir/fitness.db" ]]; then
  if [[ "$account_release" != 1 ]]; then
    python3 - "$data_dir/fitness.db" <<'PY'
import sqlite3, sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro', uri=True) as db:
    assert db.execute('SELECT COUNT(*) FROM records').fetchone()[0] == 0, 'Legacy personal records need an explicit owner mapping; migration stopped.'
PY
  fi
  systemctl stop liftlab.service || true
  if ! runuser -u liftlab -- env -u DATABASE_URL "$release_dir/.venv/bin/python" "$release_dir/scripts/backup_data.py" \
      --data-dir "$data_dir" --backup-dir "$backup_dir" --keep 7; then
    if [[ "$was_active" == 1 ]]; then systemctl start liftlab.service; fi
    echo 'Backup failed; existing release was preserved.' >&2
    exit 1
  fi
fi
# PostgreSQL migrations run with a separate owner; service only receives application credentials.
if [[ ! -f "$env_dir/migration.env" ]]; then
  echo 'Provision PostgreSQL before deploying the account release.' >&2
  if [[ "$was_active" == 1 ]]; then systemctl start liftlab.service; fi
  exit 1
fi
systemctl stop liftlab.service || true
python3 - "$env_dir/migration.env" "$release_dir" <<'PY'
import os, pathlib, subprocess, sys
env = dict(os.environ)
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith('#'):
        key, value = line.split('=', 1)
        env[key] = value
subprocess.run([sys.argv[2]+'/.venv/bin/python', '-m', 'alembic', 'upgrade', 'head'], cwd=sys.argv[2], env=env, check=True)
PY
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -d liftlab <<'SQL'
GRANT CONNECT ON DATABASE liftlab TO liftlab_app;
GRANT USAGE ON SCHEMA public TO liftlab_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO liftlab_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.alembic_version FROM liftlab_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO liftlab_app;
ALTER DEFAULT PRIVILEGES FOR ROLE liftlab_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO liftlab_app;
ALTER DEFAULT PRIVILEGES FOR ROLE liftlab_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO liftlab_app;
SQL
for name in liftlab.service liftlab-backup.service liftlab-backup.timer liftlab-mail.service liftlab-mail.timer liftlab-agent.service liftlab-agent.timer; do
  install -m 0644 "$source_dir/deploy/linux/$name" "/etc/systemd/system/$name"
done
ln -s "$release_dir" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
systemctl daemon-reload
systemctl enable liftlab.service liftlab-backup.timer liftlab-mail.timer liftlab-agent.timer
if ! systemctl restart liftlab.service; then
  echo 'Service failed to start; the health check below will restore the previous release.' >&2
fi
healthy=0
for attempt in $(seq 1 30); do
  if "$release_dir/.venv/bin/python" -c 'import json,urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2))["status"] == "ok"' >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 1
done
if [[ "$healthy" != 1 ]]; then
  systemctl stop liftlab.service
  if [[ -n "$previous" && -d "$previous" && "$previous" == "$base/releases/"* ]]; then
    ln -s "$previous" "$base/rollback.next"
    mv -Tf "$base/rollback.next" "$base/current"
    if [[ "$was_active" == 1 ]]; then systemctl start liftlab.service; fi
  fi
  echo 'New release failed its health check. Inspect: journalctl -u liftlab -n 80' >&2
  exit 1
fi
systemctl start liftlab-backup.timer
systemctl start liftlab-mail.timer
systemctl start liftlab-agent.timer
systemctl start liftlab-backup.service
"$release_dir/.venv/bin/python" - <<'PY'
import json
import urllib.request
health = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5))
assert health['mode'] == 'multi_user'
print(json.dumps({'database': 'PostgreSQL', 'authentication': True, 'listen': '127.0.0.1:8000', 'public_access': False}))
PY
echo 'Installed. Verify logs: journalctl -u liftlab -n 80'
