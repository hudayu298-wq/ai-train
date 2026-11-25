"""Fetch a pinned, checksum-verified community Windows development Redis build.

No system service or environment credentials are installed/changed. Production
uses the official Redis container or a managed service; see docs/REDIS_CACHE.md.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent.parent
VERSION='8.10.3'
URL=f'https://github.com/redis-windows/redis-windows/releases/download/{VERSION}/Redis-{VERSION}-Windows-x64-msys2.zip'
SHA256='af16df340525b431e9ec8dabfd625d5e7a233f82805b5418819904ea909c447f'


def setup():
    if os.name!='nt':raise SystemExit('Use the official Redis image/package on Linux; this installer is Windows-only.')
    folder=ROOT/'.tools/redis';folder.mkdir(parents=True,exist_ok=True)
    archive=folder/f'Redis-{VERSION}-Windows-x64-msys2.zip'
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:
        temporary=archive.with_suffix('.zip.part')
        for attempt in range(3):
            try:
                request=urllib.request.Request(URL,headers={'User-Agent':'Lianban-Development-Setup'})
                with urllib.request.urlopen(request,timeout=60) as response,temporary.open('wb') as target:
                    while block:=response.read(1024*1024):target.write(block)
                if hashlib.sha256(temporary.read_bytes()).hexdigest()!=SHA256:raise ValueError('Redis archive checksum mismatch')
                temporary.replace(archive);break
            except (OSError,ValueError):
                if attempt==2:raise
                time.sleep(1)
    destination=(folder/VERSION).resolve();destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target=(destination/member.filename).resolve()
            if not target.is_relative_to(destination) or stat.S_ISLNK(member.external_attr>>16):
                raise ValueError('Unsafe Redis archive member')
        zipped.extractall(destination)
    executables=list(destination.rglob('redis-server.exe'))
    if len(executables)!=1:raise ValueError('Expected exactly one Redis executable')
    executable=executables[0]
    config={'url':'redis://127.0.0.1:6379/0','autostart':True,'executable':str(executable),
        'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'version':VERSION,
        'source_url':URL,'archive_sha256':SHA256,'distribution':'community_windows_development_build'}
    path=ROOT/'data/redis-cache.json'
    if path.exists():raise SystemExit('Local Redis configuration already exists; refusing to overwrite it.')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    print(f'Verified Redis {VERSION} development runtime. Configuration: {path}')


if __name__=='__main__':setup()
