"""Optional Redis read-through cache. SQL remains the authority for facts/access.

No credentials, owner IDs, queries, or private JSON appear in Redis keys/logs.
Payloads use authenticated encryption; private keys additionally require the
current SQL epoch. Redis failure never prevents the original loader from running.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parents[2]
COUNTERS = Counter()
LOCK = RLock()
_down_until = 0.0
MAX_BYTES = 2_000_000


@lru_cache(maxsize=4)
def _local_config(path,modified,size):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def settings():
    url = os.environ.get('REDIS_URL')
    if not url:
        local = Path(os.environ.get('FIT_DATA_DIR', ROOT/'data'))/'redis-cache.json'
        try:
            meta=local.stat()
            url=_local_config(str(local),meta.st_mtime_ns,meta.st_size).get('url','')
        except OSError:url=''
    enabled = os.environ.get('REDIS_CACHE_ENABLED', 'true').lower() not in ('0','false','no')
    prefix = os.environ.get('REDIS_CACHE_NAMESPACE', 'lianban:cache:v1')
    if not re.fullmatch(r'[a-zA-Z0-9:_-]{1,80}', prefix):prefix='lianban:cache:v1'
    return (url if enabled else ''), prefix


def enabled():
    return bool(settings()[0])


def _count(name):
    with LOCK:COUNTERS[name] += 1


@lru_cache(maxsize=4)
def _connect(url):
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme not in ('redis','rediss') or (parsed.scheme=='redis' and parsed.hostname not in ('localhost','127.0.0.1','::1','redis')):
        raise ValueError('Remote cache requires TLS')
    return redis.Redis.from_url(url, socket_connect_timeout=.15, socket_timeout=.15,
        retry=Retry(NoBackoff(),0), max_connections=16, health_check_interval=30)


def client():
    url,_ = settings()
    if not url or time.monotonic() < _down_until:return None
    try:return _connect(url)
    except Exception:
        _failed();return None


def _failed():
    global _down_until
    _down_until = time.monotonic()+5
    _count('errors')


def _secret():
    try:from .. import auth
    except ImportError:import auth
    return auth.secret().encode()


def digest(value):
    return hmac.new(_secret(),json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()


def database_scope(url):
    return hashlib.sha256(url.render_as_string(hide_password=True).encode()).hexdigest()


def owner_prefix(scope,owner):
    return settings()[1]+':user:'+digest([scope,owner])


def _cipher(key,epoch=''):
    seed=hmac.new(_secret(),(key+'\0'+epoch).encode(),hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(seed))


def get(key,*,epoch=''):
    connection=client()
    if connection is None:return None,False
    try:
        raw=connection.get(key)
        if raw is None:
            _count('misses');return None,False
        if len(raw)>MAX_BYTES:raise ValueError('Oversized cache entry')
        value=json.loads(_cipher(key,epoch).decrypt(raw))
        _count('hits');return value,True
    except (InvalidToken,ValueError,TypeError):
        _count('invalid_entries');return None,False
    except Exception:
        _failed();return None,False


def put(key,value,ttl,*,epoch='',owner_index=None):
    connection=client()
    if connection is None:return
    try:
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        if len(raw)>MAX_BYTES-1024:return
        encrypted=_cipher(key,epoch).encrypt(raw)
        with connection.pipeline(transaction=True) as pipe:
            pipe.set(key,encrypted,ex=ttl)
            if owner_index:
                pipe.sadd(owner_index,key);pipe.expire(owner_index,ttl+30)
            pipe.execute()
        _count('writes')
    except (TypeError,ValueError):_count('uncacheable')
    except Exception:_failed()


def purge_private(scope,owner):
    connection=client()
    if connection is None:return
    index=owner_prefix(scope,owner)+':index'
    try:
        keys=list(connection.smembers(index))
        for offset in range(0,len(keys),128):connection.unlink(*keys[offset:offset+128])
        connection.unlink(index)
        _count('invalidations')
    except Exception:_failed()


def public_key(scope,kind,identity):
    return settings()[1]+':'+kind+':'+digest([scope,identity])


def status():
    connection=client();available=False
    if connection is not None:
        try:available=bool(connection.ping())
        except Exception:_failed()
    return {'configured':enabled(),'available':available,'fallback':'database_and_local_files',
        'counters':dict(COUNTERS),'private_payloads':'encrypted','user_ttl_seconds':120,'knowledge_ttl_seconds':600}
