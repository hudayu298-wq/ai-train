"""Versioned prompt assets and a source fingerprint for evaluation publication gates."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = json.loads((ROOT / 'prompts' / 'versions.json').read_text(encoding='utf-8'))


def version(name):
    return VERSIONS[name]


@lru_cache(maxsize=64)
def _asset(relative,modified,size,changed):
    from . import cache
    text=(ROOT/'prompts'/relative).read_text(encoding='utf-8')
    digest=hashlib.sha256(text.encode()).hexdigest()
    if cache.enabled():
        key=cache.public_key(str(ROOT),'prompt',[relative,digest])
        value,hit=cache.get(key)
        if hit and isinstance(value,str) and hashlib.sha256(value.encode()).hexdigest()==digest:return value,digest
        cache.put(key,text,3600)
    return text,digest


def text(relative):
    """L1 file cache plus shared, authenticated Redis cache; changes get new keys."""
    path=(ROOT/'prompts'/relative).resolve()
    if not path.is_relative_to((ROOT/'prompts').resolve()) or not path.is_file():
        raise ValueError('Unknown prompt asset')
    meta=path.stat()
    return _asset(relative,meta.st_mtime_ns,meta.st_size,meta.st_ctime_ns)[0]


def runtime_fingerprint():
    paths = [p for p in ROOT.glob('*.py') if not p.name.startswith('test_')]
    paths += list((ROOT / 'services').glob('*.py')) + list((ROOT / 'prompts').glob('*'))
    paths += [p for p in (ROOT / 'data').rglob('*') if p.is_file() and any(part.startswith('knowledge') for part in p.relative_to(ROOT/'data').parts)]
    paths += list((ROOT / 'policies').glob('*.json'))
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
