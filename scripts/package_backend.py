"""Build a deployable archive without credentials, local records or SDKs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {'__pycache__', '.pytest_cache', '.git', '.venv', '.tools'}
DIRECTORIES = ('backend', 'preview', 'deploy/linux')
FILES = ('.env.example', 'alembic.ini', 'scripts/backup_data.py', 'scripts/send_mail.py', 'scripts/manage_account.py', 'scripts/agent_worker.py', 'scripts/download_retrieval_models.py')


def build_package(output_dir: Path) -> dict:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    release = f'{stamp}-{revision}'
    archive_path = output_dir / f'liftlab-{release}.tar.gz'
    paths = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        for path in (ROOT / directory).rglob('*'):
            rel = path.relative_to(ROOT)
            if (path.is_file() and not path.is_symlink()
                    and not any(part in EXCLUDED for part in rel.parts)
                    and path.suffix.lower() not in {'.pyc', '.db', '.sqlite', '.pem', '.key'}
                    and not path.name.startswith('.env')):
                paths.append(path)
    paths = sorted(set(paths))
    manifest = {'release': release, 'git_revision': revision, 'working_tree_dirty': dirty,
                'files': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in paths}}
    manifest_path = output_dir / 'RELEASE.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    with tarfile.open(archive_path, 'x:gz', format=tarfile.PAX_FORMAT) as archive:
        for path in paths:
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
        archive.add(manifest_path, arcname='RELEASE.json', recursive=False)
    result = {'archive': str(archive_path), 'release': release, 'file_count': len(paths),
              'sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest()}
    (output_dir / 'package.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.tools/deployments/latest')
    args = parser.parse_args()
    print(json.dumps(build_package(args.output_dir), indent=2))
