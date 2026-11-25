"""SQLAlchemy storage. Private records always require an authenticated owner."""
import os
import json
from copy import deepcopy
from uuid import uuid4
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Index,
                        Integer, JSON, MetaData, String, Table, UniqueConstraint,
                        create_engine, delete, event, insert, select, update)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
document = JSON().with_variant(JSONB(), 'postgresql')
owner_context = ContextVar('liftlab_owner', default=None)
session_context = ContextVar('liftlab_session', default=None)

users = Table('users', metadata,
    Column('id', String(36), primary_key=True),
    Column('email', String(254), unique=True),
    Column('password_hash', String(512)),
    Column('display_name', String(100), nullable=False, default='训练者'),
    Column('role', String(20), nullable=False, default='user'),
    Column('active', Boolean, nullable=False, default=True),
    Column('created_at', DateTime(timezone=True), nullable=False))
identities = Table('auth_identities', metadata,
    Column('provider', String(80), primary_key=True),
    Column('subject', String(200), primary_key=True),
    Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True))
sessions = Table('auth_sessions', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('device_name', String(100), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('last_used_at', DateTime(timezone=True), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('revoked', Boolean, nullable=False, default=False))
refresh_tokens = Table('refresh_tokens', metadata,
    Column('digest', String(64), primary_key=True),
    Column('session_id', ForeignKey('auth_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('used', Boolean, nullable=False, default=False))
challenges = Table('auth_challenges', metadata,
    Column('id', String(64), primary_key=True),
    Column('purpose', String(30), nullable=False),
    Column('subject', String(254), nullable=False, index=True),
    Column('digest', String(64), nullable=False),
    Column('payload', document, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('attempts', Integer, nullable=False, default=0),
    Column('consumed', Boolean, nullable=False, default=False))
rate_buckets = Table('auth_rate_buckets', metadata,
    Column('key', String(100), primary_key=True),
    Column('hits', Integer, nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False))
outbox = Table('mail_outbox', metadata,
    Column('id', String(36), primary_key=True),
    Column('recipient_digest', String(64), nullable=False),
    Column('encrypted_message', String, nullable=False),
    Column('attempts', Integer, nullable=False, default=0),
    Column('available_at', DateTime(timezone=True), nullable=False),
    Column('sent', Boolean, nullable=False, default=False))
ai_leases = Table('ai_leases', metadata,
    Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('lease_id', String(36), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False))
consents = Table('consent_records', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('version', String(40), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False))
records_table = Table('user_records', metadata,
    Column('seq', BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True),
    Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('id', String(120), nullable=False),
    Column('kind', String(50), nullable=False),
    Column('payload', document, nullable=False),
    UniqueConstraint('user_id', 'kind', 'id'),
    Index('user_records_owner_kind_seq', 'user_id', 'kind', 'seq'))
catalog = Table('catalog_items_v2', metadata,
    Column('kind', String(30), primary_key=True), Column('id', String(100), primary_key=True),
    Column('name', String(100), nullable=False), Column('category', String(80), nullable=False),
    Column('active', Boolean, nullable=False, default=True),
    Column('sort_order', Integer, nullable=False, default=0),
    Column('payload', document, nullable=False))
measurements = Table('health_measurements', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('metric', String(40), nullable=False),
    Column('provider', String(60), nullable=False),
    Column('external_id', String(120), nullable=False),
    Column('observed_at', DateTime(timezone=True), nullable=False),
    Column('source_updated_at', DateTime(timezone=True), nullable=False),
    Column('payload', document, nullable=False),
    UniqueConstraint('user_id', 'provider', 'external_id'),
    Index('health_measurements_owner_metric_time', 'user_id', 'metric', 'observed_at'))
research_records = Table('research_records', metadata,
    Column('kind', String(30), primary_key=True), Column('id', String(100), primary_key=True),
    Column('status', String(30), nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False),
    Column('payload', document, nullable=False),
    Index('research_records_kind_status', 'kind', 'status'))
knowledge_chunks = Table('knowledge_chunks', metadata,
    Column('id', String(64), primary_key=True),
    Column('bundle_hash', String(64), nullable=False),
    Column('model_hash', String(64), nullable=False),
    Column('item_id', String(80), nullable=False),
    Column('chunk_key', String(160), nullable=False),
    Column('content', String, nullable=False),
    Column('content_hash', String(64), nullable=False),
    Column('embedding', document, nullable=False),
    Column('payload', document, nullable=False),
    Index('knowledge_chunks_bundle_model', 'bundle_hash', 'model_hash'))
engines = {}


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def owner():
    value = owner_context.get()
    if not value:
        raise HTTPException(401, '请先登录')
    return value


def get_engine(path=None):
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        path = Path(path or Path(os.environ.get('FIT_DATA_DIR', 'data')) / 'fitness-v2.db').resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        url = 'sqlite:///' + path.as_posix()
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if url not in engines:
        kwargs = {'pool_pre_ping': True, 'hide_parameters': True}
        if url.startswith('sqlite:'):
            from sqlalchemy.pool import NullPool
            kwargs['connect_args'] = {'check_same_thread': False, 'timeout': 30}
            kwargs['poolclass'] = NullPool
        else:
            kwargs.update(pool_size=5, max_overflow=5, hide_parameters=True)
        engine = create_engine(url, **kwargs)
        if engine.dialect.name == 'sqlite':
            @event.listens_for(engine, 'connect')
            def foreign_keys(dbapi, _):
                dbapi.execute('PRAGMA foreign_keys=ON')
        engines[url] = engine
    return engines[url]


class Store:
    def __init__(self, conn):
        self.conn = conn
        self._private_dirty = False
        self._memo = {}
        self._purges = set()

    def invalidate_private_cache(self):
        """Epoch and business mutation commit/rollback together; Redis is optional."""
        try:from .services import cache
        except ImportError:from services import cache
        self._private_dirty = True
        self._memo.clear()
        self._purges.add((cache.database_scope(self.conn.engine.url),owner()))
        stmt=dialect_insert(self.conn,records_table).values(user_id=owner(),kind='cache_meta',id='redis_epoch',payload={'nonce':uuid4().hex})
        self.conn.execute(stmt.on_conflict_do_update(index_elements=['user_id','kind','id'],set_={'payload':stmt.excluded.payload}))

    def cached_user(self, name, parameters, loader):
        try:from .services import cache
        except ImportError:from services import cache
        # Always read current SQL access/epoch, including on a Redis/local hit.
        joined=users.outerjoin(records_table,(records_table.c.user_id==users.c.id)&
            (records_table.c.kind=='cache_meta')&(records_table.c.id=='redis_epoch'))
        state=self.conn.execute(select(users.c.active,records_table.c.payload).select_from(joined).where(users.c.id==owner())).mappings().first()
        if not state or not state['active']:raise HTTPException(401,'账号已停用，请重新登录')
        memo_key=(owner(),name,json.dumps(parameters,sort_keys=True))
        if memo_key in self._memo:return deepcopy(self._memo[memo_key])
        epoch=(state['payload'] or {}).get('nonce')
        if cache.enabled() and not epoch:
            self.lock_user()
            self.invalidate_private_cache()
        prefix=cache.owner_prefix(cache.database_scope(self.conn.engine.url),owner()) if cache.enabled() else ''
        key=prefix+':data:'+cache.digest([epoch,name,parameters]) if prefix and epoch else ''
        value,hit=cache.get(key,epoch=epoch) if key and not self._private_dirty else (None,False)
        if not hit:
            value=loader()
            # Never put uncommitted business changes or a newly initialized epoch
            # into Redis; next transaction may safely fill it after commit.
            if key and not self._private_dirty:cache.put(key,value,120,epoch=epoch,owner_index=prefix+':index')
        self._memo[memo_key]=deepcopy(value)
        return deepcopy(value)

    def clear_committed_cache(self):
        try:from .services import cache
        except ImportError:from services import cache
        for scope,uid in self._purges:cache.purge_private(scope,uid)

    def lock_user(self):
        # Serializes a user's atomic profile/chat/workout updates, including deletion.
        row = self.conn.execute(select(users.c.id).where(
            users.c.id == owner(), users.c.active.is_(True)).with_for_update()).first()
        if not row:
            raise HTTPException(401, '账号已停用，请重新登录')
        try:from .services import privacy
        except ImportError:from services import privacy
        privacy.check_guard(self)
        sid = session_context.get()
        if sid:
            session = self.conn.execute(select(sessions).where(
                sessions.c.id == sid, sessions.c.user_id == owner(), sessions.c.revoked.is_(False))).mappings().first()
            if not session or aware(session['expires_at']) <= now():
                raise HTTPException(401, '登录已失效，请重新登录')

    def read(self, kind, key):
        return self.conn.execute(select(records_table.c.payload).where(
            records_table.c.user_id == owner(), records_table.c.kind == kind,
            records_table.c.id == key)).scalar_one_or_none()

    def records(self, kind, limit=None):
        query = select(records_table.c.id, records_table.c.payload).where(
            records_table.c.user_id == owner(), records_table.c.kind == kind).order_by(records_table.c.seq.desc())
        if limit is not None:
            query = query.limit(limit)
        return [{'id': row.id, **row.payload} for row in self.conn.execute(query)]

    def write(self, kind, key, payload, replace=True):
        self.lock_user()
        if kind in ('profile','coach_profile','workout','training','health_settings','mobility_settings','nutrition_settings'):
            self.invalidate_private_cache()
        values = dict(user_id=owner(), kind=kind, id=key, payload=payload)
        statement = dialect_insert(self.conn, records_table).values(**values)
        if replace:
            statement = statement.on_conflict_do_update(
                index_elements=['user_id', 'kind', 'id'], set_={'payload': payload})
        self.conn.execute(statement)

    def remove(self, kind, key):
        self.lock_user()
        if kind in ('profile','coach_profile','workout','training','health_settings','mobility_settings','nutrition_settings'):
            self.invalidate_private_cache()
        return self.conn.execute(delete(records_table).where(records_table.c.user_id == owner(),
            records_table.c.kind == kind, records_table.c.id == key)).rowcount

    def catalog_read(self, kind, key=None, active=True):
        query = select(catalog.c.payload).where(catalog.c.kind == kind)
        if active:
            query = query.where(catalog.c.active.is_(True))
        if key is not None:
            return self.conn.execute(query.where(catalog.c.id == key)).scalar_one_or_none()
        return list(self.conn.execute(query.order_by(catalog.c.sort_order, catalog.c.id)).scalars())

    def catalog_write(self, kind, payload, ignore=False, order=10000):
        statement = dialect_insert(self.conn, catalog).values(kind=kind, id=payload['id'], name=payload['name'],
            category=payload['category'], active=True, sort_order=order, payload=payload)
        if ignore:
            statement = statement.on_conflict_do_nothing(index_elements=['kind', 'id'])
        self.conn.execute(statement)

    def catalog_seed(self,kind,entries):
        # Fixed batches stay below conservative SQLite bind-parameter limits.
        # Existing edits and archived entries win over the immutable seed.
        for offset in range(0,len(entries),100):
            values=[dict(kind=kind,id=p['id'],name=p['name'],category=p['category'],
                active=True,sort_order=offset+i,payload=p) for i,p in enumerate(entries[offset:offset+100])]
            statement=dialect_insert(self.conn,catalog).values(values)
            self.conn.execute(statement.on_conflict_do_nothing(index_elements=['kind','id']))

    def catalog_update(self, kind, key, **values):
        return self.conn.execute(update(catalog).where(catalog.c.kind == kind,
            catalog.c.id == key, catalog.c.active.is_(True)).values(**values)).rowcount


def dialect_insert(conn, table):
    if conn.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert as dialect
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect
    return dialect(table)


@contextmanager
def connection(path=None):
    with get_engine(path).begin() as conn:
        store=Store(conn)
        yield store
    store.clear_committed_cache()
