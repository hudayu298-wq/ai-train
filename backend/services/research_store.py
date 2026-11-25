"""Shared research registry; publication is separate from untrusted source ingestion."""
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

try:
    from .. import database as d
except ImportError:
    import database as d


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require_admin(db):
    user = db.conn.execute(select(d.users).where(d.users.c.id == d.owner(), d.users.c.active.is_(True))).mappings().first()
    if not user or user['role'] != 'admin':
        raise HTTPException(403, '仅管理员可运行研究、评测和发布知识')
    return user


def get(db, kind, key):
    row = db.conn.execute(select(d.research_records).where(d.research_records.c.kind == kind,
        d.research_records.c.id == key)).mappings().first()
    return {'id': row['id'], 'status': row['status'], **row['payload']} if row else None


def listing(db, kind, status=None, limit=100):
    query = select(d.research_records).where(d.research_records.c.kind == kind)
    if status:
        query = query.where(d.research_records.c.status == status)
    rows = db.conn.execute(query.order_by(d.research_records.c.updated_at.desc()).limit(limit)).mappings()
    return [{'id': r['id'], 'status': r['status'], **r['payload']} for r in rows]


def put(db, kind, key, value, status):
    payload = {k: v for k, v in value.items() if k not in ('id', 'status')}
    stmt = d.dialect_insert(db.conn, d.research_records).values(kind=kind, id=key,
        status=status, updated_at=d.now(), payload=payload)
    db.conn.execute(stmt.on_conflict_do_update(index_elements=['kind', 'id'],
        set_={'payload': payload, 'status': status, 'updated_at': d.now()}))
    return {'id': key, 'status': status, **payload}


DEFAULT_POLICY = {'answer_style': 'balanced', 'retrieval_limit': 3, 'clarification_limit': 1, 'show_sources': True}


def active(db):
    pointer = get(db, 'pointer', 'active')
    release = get(db, 'release', pointer['release_id']) if pointer else None
    return release or {'id': 'baseline', 'status': 'published', 'policy': DEFAULT_POLICY, 'evidence': [], 'version': 1}


def lock_publication(db):
    stmt = d.dialect_insert(db.conn, d.research_records).values(kind='pointer', id='active',
        status='active', updated_at=d.now(), payload={'release_id': 'baseline'})
    db.conn.execute(stmt.on_conflict_do_nothing(index_elements=['kind', 'id']))
    db.conn.execute(select(d.research_records.c.id).where(d.research_records.c.kind == 'pointer',
        d.research_records.c.id == 'active').with_for_update()).one()


def eligible(db, item):
    document = get(db, 'document', item['document_id'])
    evidence = get(db, 'evidence', item['id'])
    return bool(document and document['status'] != 'superseded' and not document['retraction_detected']
        and evidence and evidence['status'] == 'reviewed')


def retrieve(db, query, limit=None, release=None):
    import re
    release = release or active(db)
    terms = set(re.findall(r'[a-zA-Z]{3,}', query.lower()))
    chinese = ''.join(re.findall(r'[\u4e00-\u9fff]', query))
    terms.update(chinese[i:i+2] for i in range(len(chinese)-1))
    ranked = []
    for item in release['evidence']:
        if not eligible(db, item):
            continue
        text = ' '.join(str(item.get(k, '')) for k in ('title', 'claim', 'population', 'intervention', 'outcome', 'keywords')).lower()
        score = sum(term in text for term in terms)
        if score or not query:
            ranked.append((score, item))
    ranked.sort(key=lambda v: (-v[0], v[1]['id']))
    return [item for _, item in ranked[:limit or release['policy']['retrieval_limit']]]


def enqueue(db, kind, payload):
    require_admin(db)
    lock_publication(db)
    jobs = [j for j in listing(db, 'job', limit=2000) if j.get('created_at', '')[:10] == d.now().date().isoformat()]
    evaluation_kinds=('evaluation','knowledge_evaluation','retrieval_evaluation')
    if len(jobs) >= 8 or kind in evaluation_kinds and sum(j['job_type'] in evaluation_kinds for j in jobs) >= 2:
        raise HTTPException(429, '今日研究任务预算已用完（8项任务、其中最多2次完整评测）')
    key = str(uuid4())
    return put(db, 'job', key, {'job_type': kind, 'input': payload, 'actor_id': d.owner(),
        'created_at': d.now().isoformat(), 'attempts': 0}, 'queued')
