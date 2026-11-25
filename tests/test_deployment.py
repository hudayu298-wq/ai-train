import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tarfile

import pytest

from scripts.backup_data import create_backup
from scripts import package_backend


def test_backup_copies_committed_sqlite_rows_and_uploaded_files(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','')
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'uploads').mkdir()
    (data / 'uploads/meal.png').write_bytes(b'uploaded-test-image')
    (data / '.env').write_text('NOT_A_REAL_SECRET=not-for-backup', encoding='utf-8')
    with closing(sqlite3.connect(data / 'fitness.db')) as db:
        db.execute('CREATE TABLE records (value TEXT)')
        db.execute("INSERT INTO records VALUES ('committed')")
        db.commit()
        db.execute("INSERT INTO records VALUES ('uncommitted')")
        target = create_backup(data, tmp_path / 'backups')
        db.rollback()
    with tarfile.open(target) as archive:
        assert set(archive.getnames()) == {'fitness.db', 'uploads/meal.png'}
        restored = tmp_path / 'restore.db'
        restored.write_bytes(archive.extractfile('fitness.db').read())
        assert archive.extractfile('uploads/meal.png').read() == b'uploaded-test-image'
    with closing(sqlite3.connect(restored)) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT value FROM records').fetchall() == [('committed',)]


def test_backup_retention_preserves_unrelated_files_and_rejects_nested_output(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','')
    data = tmp_path / 'data'
    data.mkdir()
    with closing(sqlite3.connect(data / 'fitness.db')) as db:
        db.execute('CREATE TABLE records (value TEXT)')
        db.commit()
    backups = tmp_path / 'backups'
    backups.mkdir()
    unrelated = backups / 'manual-backup.tar.gz'
    unrelated.write_bytes(b'leave-this-file-alone')
    first = create_backup(data, backups, keep=2)
    second = create_backup(data, backups, keep=2)
    third = create_backup(data, backups, keep=2)
    assert not first.exists() and second.exists() and third.exists()
    assert unrelated.read_bytes() == b'leave-this-file-alone'
    with pytest.raises(ValueError, match='outside'):
        create_backup(data, data / 'backups')


def test_deployment_archive_contains_seed_data_but_excludes_runtime_and_credentials(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    files = {
        '.env.example': 'AI_API_KEY=\n',
        '.env': 'do-not-package',
        'backend/app.py': 'app = None\n',
        'backend/data/foods.json': '[]',
        'backend/data/exercises.json': '[]',
        'backend/.env.production': 'do-not-package',
        'backend/key.pem': 'not-a-real-key',
        'backend/fitness.db': 'not-a-real-database',
        'backend/__pycache__/app.pyc': 'not-source',
        'data/fitness.db': 'private-user-records',
        'preview/index.html': '<html></html>',
        'deploy/linux/install.sh': '#!/bin/bash\n',
        'scripts/backup_data.py': '# backup script\n',
        'scripts/send_mail.py': '# mail worker\n',
        'scripts/manage_account.py': '# interactive operator tool\n',
        'scripts/agent_worker.py': '# bounded agent/research worker\n',
        'scripts/download_retrieval_models.py': '# pinned model assets\n',
        'alembic.ini': '[alembic]\n',
        '.tools/credentials.txt': 'private-local-tools',
    }
    for name, content in files.items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    monkeypatch.setattr(package_backend, 'ROOT', project)
    monkeypatch.setattr(package_backend.subprocess, 'check_output',
                        lambda args, **kwargs: '123456789abc\n' if kwargs.get('text') else b'?? deployment\n')
    result = package_backend.build_package(tmp_path / 'package')
    with tarfile.open(result['archive']) as archive:
        names = set(archive.getnames())
        assert names == {'.env.example', 'backend/app.py', 'backend/data/foods.json',
                         'backend/data/exercises.json', 'preview/index.html',
                         'deploy/linux/install.sh', 'scripts/backup_data.py', 'scripts/send_mail.py', 'scripts/manage_account.py', 'scripts/agent_worker.py', 'scripts/download_retrieval_models.py', 'alembic.ini', 'RELEASE.json'}
        manifest = json.load(archive.extractfile('RELEASE.json'))
        assert manifest['working_tree_dirty'] is True
        assert set(manifest['files']) == names - {'RELEASE.json'}
