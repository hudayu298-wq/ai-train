"""Pinned portable PostgreSQL 16 for disposable LOCAL acceptance, no service install.

Archive source is EDB, linked by postgresql.org/download/windows/. Published
checksum: github.com/EnterpriseDB/edb-installers/issues/731.
"""
import hashlib
from pathlib import Path
import stat
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent.parent
VERSION='16.15-5'
URL=f'https://get.enterprisedb.com/postgresql/postgresql-{VERSION}-windows-x64-binaries.zip'
SHA256='43bb45f173a6f08cf1d29a97a6d8deb119e8e8093a24c00d2d1001a0ccaa8281'


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(2*1024*1024):value.update(block)
    return value.hexdigest()


def setup():
    folder=ROOT/'.tools/postgres-audit';folder.mkdir(parents=True,exist_ok=True)
    archive=folder/f'postgresql-{VERSION}.zip'
    if not archive.exists() or digest(archive)!=SHA256:
        temporary=archive.with_suffix('.zip.part')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(URL,timeout=45) as response,temporary.open('wb') as target:
                    while block:=response.read(2*1024*1024):target.write(block)
                if digest(temporary)!=SHA256:raise ValueError('PostgreSQL archive checksum mismatch')
                temporary.replace(archive);break
            except (OSError,ValueError):
                if attempt==2:raise
                time.sleep(1)
    destination=(folder/VERSION).resolve();destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target=(destination/member.filename).resolve()
            if not target.is_relative_to(destination) or stat.S_ISLNK(member.external_attr>>16):
                raise ValueError('Unsafe PostgreSQL archive member')
        # Server, command-line tools, libraries and timezone/catalog assets only.
        for member in zipped.infolist():
            if member.filename.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/')):zipped.extract(member,destination)
    if not (destination/'pgsql/bin/postgres.exe').is_file():raise ValueError('PostgreSQL binary missing')
    print(f'Verified portable PostgreSQL {VERSION}: {destination}')
    return destination/'pgsql/bin'


if __name__=='__main__':setup()
