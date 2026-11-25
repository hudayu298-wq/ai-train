"""Back up PostgreSQL (or local SQLite) with uploaded media; never credentials."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
import tarfile
import tempfile
import subprocess
from urllib.parse import urlsplit, unquote
from uuid import uuid4

BACKUP_NAME = re.compile(r'liftlab-\d{8}T\d{12}Z-[0-9a-f]{8}\.tar\.gz')


def create_backup(data_dir: Path, backup_dir: Path, keep: int = 7) -> Path:
    data_dir = data_dir.resolve(strict=True)
    backup_dir = backup_dir.resolve()
    if backup_dir == data_dir or backup_dir.is_relative_to(data_dir):
        raise ValueError('Backup directory must be outside the application data directory')
    if keep < 1:
        raise ValueError('At least one backup must be retained')
    postgres = os.environ.get('DATABASE_URL', '').startswith('postgresql')
    source = data_dir / ('fitness-v2.db' if (data_dir / 'fitness-v2.db').exists() else 'fitness.db')
    if not postgres and (not source.is_file() or source.is_symlink()):
        raise ValueError('Expected a regular fitness.db file in the data directory')
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    name = f'liftlab-{stamp}-{uuid4().hex[:8]}.tar.gz'
    target = backup_dir / name
    # TemporaryDirectory only removes the directory it created inside backup_dir.
    with tempfile.TemporaryDirectory(prefix='.liftlab-', dir=backup_dir) as temp:
        temp_path = Path(temp).resolve()
        assert temp_path.is_relative_to(backup_dir)
        snapshot = temp_path / ('database.dump' if postgres else source.name)
        guard = None
        if postgres:
            import psycopg
            parsed = urlsplit(os.environ['DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:', 1))
            env = {**os.environ, 'PGHOST': parsed.hostname or '127.0.0.1', 'PGPORT': str(parsed.port or 5432),
                'PGUSER': unquote(parsed.username or ''), 'PGPASSWORD': unquote(parsed.password or ''),
                'PGDATABASE': parsed.path.lstrip('/')}
            guard = psycopg.connect(host=env['PGHOST'], port=env['PGPORT'], user=env['PGUSER'],
                password=env['PGPASSWORD'], dbname=env['PGDATABASE'],connect_timeout=5)
            # Private mutations use SELECT FOR UPDATE on users (ROW SHARE).
            # EXCLUSIVE conflicts with that lock while allowing pg_dump reads;
            # SHARE would allow those mutations during DB/media collection.
            try:
                guard.execute("SET LOCAL lock_timeout='15s'")
                guard.execute('LOCK TABLE users IN EXCLUSIVE MODE')
                result = subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(snapshot)],
                    env=env, capture_output=True,timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if result.returncode:
                    raise RuntimeError('PostgreSQL backup failed; inspect database connectivity without logging credentials')
            except Exception:
                guard.close()
                raise
        else:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as reader:
                with closing(sqlite3.connect(snapshot)) as writer:
                    reader.backup(writer)
                    if writer.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('Database backup failed the SQLite integrity check')
        archive_path = temp_path / name
        try:
            with tarfile.open(archive_path, 'w:gz') as archive:
                archive.add(snapshot, arcname=snapshot.name, recursive=False)
                uploads = data_dir / 'uploads'
                if uploads.is_dir() and not uploads.is_symlink():
                    for path in sorted(uploads.rglob('*')):
                        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(uploads.resolve()):
                            archive.add(path, arcname=path.relative_to(data_dir).as_posix(), recursive=False)
        finally:
            if guard is not None:
                guard.close()
        os.chmod(archive_path, 0o600)
        archive_path.replace(target)
    # Delete only archives made by this utility; leave unrelated files untouched.
    archives = sorted((p for p in backup_dir.iterdir()
                       if p.is_file() and not p.is_symlink() and BACKUP_NAME.fullmatch(p.name)),
                      key=lambda p: p.name, reverse=True)
    for old in archives[keep:]:
        assert old.resolve().parent == backup_dir
        old.unlink()
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--keep', type=int, default=7)
    args = parser.parse_args()
    print(create_backup(args.data_dir, args.backup_dir, args.keep))
