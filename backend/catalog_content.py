"""Version-bound public name/description proposals; separate from scientific knowledge."""
import hashlib,json
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field
try:
    from .services import research_store as store
except ImportError:
    from services import research_store as store

class Proposal(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    exercise_id:str=Field(min_length=1,max_length=80)
    language:Literal['zh','en']
    name:str=Field(min_length=1,max_length=100)
    description:str=Field(default='',max_length=1500)
    source_note:str=Field(min_length=5,max_length=500)
    share_publicly:Literal[True]
class Review(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    approved:bool
    notes:str=Field(min_length=5,max_length=500)

def fingerprint(entry):
    return hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def decorate(entry,language,published,source_hash=None):
    result=dict(entry)
    if result.get('source_kind')=='user':return result
    content=published.get(entry['id']+'_'+language)
    if content and content.get('status')=='published' and content.get('base_hash')==source_hash:
        result['aliases']=list(dict.fromkeys([*result.get('aliases',[]),result['name']]))
        result.update(name=content['name'],summary=content['description'] or result.get('summary',''),
            translation_version=content['proposal_id'],translation_status='editorial_reviewed_not_scientific')
    elif language=='en' and result.get('original_name'):
        result['name']=result['original_name']
    return result

def published(db):return {r['id']:r for r in store.listing(db,'exercise_locale',limit=10000)}

def router(connection):
    api=APIRouter(prefix='/api/catalog-content')
    @api.get('')
    def listing():
        with connection() as db:return {'items':store.listing(db,'locale_proposal')}
    @api.post('')
    def propose(body:Proposal):
        with connection() as db:
            db.lock_user();entry=db.catalog_read('exercises',body.exercise_id)
            if not entry:raise HTTPException(404,'动作不存在')
            value={**body.model_dump(exclude={'share_publicly'}),'base_hash':fingerprint(entry)}
            return store.put(db,'locale_proposal',uuid4().hex,value,'pending')
    @api.post('/{key}/review')
    def review(key:str,body:Review):
        with connection() as db:
            reviewer=store.require_admin(db);store.put(db,'catalog_lock','content',{},'locked')
            proposal=store.get(db,'locale_proposal',key)
            if not proposal:raise HTTPException(404,'待审条目不存在')
            if proposal['status']!='pending':raise HTTPException(409,'条目已处理，请刷新')
            entry=db.catalog_read('exercises',proposal['exercise_id'])
            if not entry or fingerprint(entry)!=proposal['base_hash']:raise HTTPException(409,'来源已修改或停用，须重新提交')
            reviewed={**proposal,'review_notes':body.notes,'reviewer_id':reviewer['id'],'reviewed_at':store.d.now().isoformat()}
            store.put(db,'locale_proposal',key,reviewed,'approved' if body.approved else 'rejected')
            if body.approved:
                store.put(db,'exercise_locale',proposal['exercise_id']+'_'+proposal['language'],
                    {**reviewed,'proposal_id':key},'published')
            return {'status':'published' if body.approved else 'rejected'}
    @api.post('/{key}/withdraw')
    def withdraw(key:str):
        with connection() as db:
            reviewer=store.require_admin(db);store.put(db,'catalog_lock','content',{},'locked')
            proposal=store.get(db,'locale_proposal',key)
            if not proposal:raise HTTPException(404,'条目不存在')
            pointer=store.get(db,'exercise_locale',proposal['exercise_id']+'_'+proposal['language'])
            if not pointer or pointer.get('proposal_id')!=key:raise HTTPException(409,'该版本已被其他版本替换')
            store.put(db,'exercise_locale',pointer['id'],pointer,'withdrawn')
            store.put(db,'locale_proposal',key,proposal,'withdrawn')
            return {'status':'withdrawn'}
    return api
