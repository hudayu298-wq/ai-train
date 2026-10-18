"""Frozen initial schema. Do not edit after revision 0001 has been deployed."""
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Index,
    Integer, JSON, MetaData, String, Table, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
document = JSON().with_variant(JSONB(), 'postgresql')

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
