"""Read-only OFF adapter. Confirmed food choices are owner data, never meals."""
import math,os,re
from datetime import datetime,timedelta,timezone
from typing import Literal
import httpx
from fastapi import APIRouter,HTTPException
from sqlalchemy import case, or_
from pydantic import BaseModel,ConfigDict
try:
    from . import database as d,library
except ImportError:
    import database as d
    import library

class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed:Literal[True]

def normalize(product,barcode):
    if product.get('nutrition_data_per')!='100g':
        raise HTTPException(422,'目前只接入明确每100克的营养标签；每份或每100毫升请手工核对录入')
    n=product.get('nutriments') or {}
    nutrition=product.get('nutrition') or {}
    aggregate=nutrition.get('aggregated_set') or {}
    facts=aggregate.get('nutrients') or {}
    if facts:
        if aggregate.get('preparation','as_sold')!='as_sold':
            raise HTTPException(422,'当前只接入售卖状态的每100克标签，不混用冲调后的营养值')
        n={}
        for nutrient,unit in [('energy-kcal','kcal'),('proteins','g'),('fat','g'),('carbohydrates','g')]:
            fact=facts.get(nutrient) or {}
            if fact.get('source') not in ('manufacturer','packaging','label') or fact.get('source_per')!='100g' or fact.get('unit')!=unit or fact.get('modifier'):
                raise HTTPException(422,'需要来自包装或厂商的明确每100克数据，不采用估算或模糊值')
            n[nutrient+'_100g']=fact.get('value')
    keys={'kcal':'energy-kcal_100g','protein':'proteins_100g','fat':'fat_100g','carbs':'carbohydrates_100g'}
    values={}
    for key,field in keys.items():
        value=n.get(field)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise HTTPException(422,'外部标签营养数据不完整，不能用0补齐')
        values[key]=value
    if product.get('code') and str(product['code'])!=barcode:raise HTTPException(502,'来源返回的条码不一致')
    name=product.get('product_name_zh') or product.get('product_name')
    if not isinstance(name,str) or not name.strip():raise HTTPException(422,'外部产品缺少名称，请手工录入')
    source='https://world.openfoodfacts.org/product/'+barcode
    try:
        entry=library.FoodEntry(id='off_'+barcode,name=name[:100],category='包装食品',state='prepared',
            source_label='Open Food Facts · ODbL · '+source,
            notes='每100克标签数据，社区贡献，需核对包装；不代表营养处方。',**values).model_dump()
    except ValueError:raise HTTPException(422,'外部营养值不符合质量检查，请手工核对') from None
    return {**entry,'basis_g':100,'source_kind':'open_food_facts','review_status':'external_unreviewed',
        'source_url':source,'source_license':'ODbL-1.0 / DbCL','barcode':barcode}

async def fetch(barcode):
    # Fixed host/path and no user records in outbound requests; never write to OFF.
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        response=await client.get('https://world.openfoodfacts.org/api/v3.6/product/'+barcode+'.json',
            headers={'User-Agent':os.environ.get('OFF_USER_AGENT','Lianban/0.5.1 (https://lianbanfit.top)')},
            params={'fields':'code,product_name,product_name_zh,nutrition_data_per,nutriments,nutrition'})
        response.raise_for_status()
        return response.json()

def check_barcode(barcode):
    if not re.fullmatch(r'[0-9]{8,14}',barcode):raise HTTPException(422,'请填写8至14位商品条码数字')

def router(connection):
    api=APIRouter(prefix='/api/external-foods')
    @api.get('/{barcode}')
    async def lookup(barcode:str):
        check_barcode(barcode)
        with connection() as db:
            cached=db.read('external_food_candidate',barcode)
            if cached and datetime.fromisoformat(cached['expires_at'])>datetime.now(timezone.utc):return cached
        # Shared provider limit: no automatic retries/search-as-you-type.
        with connection() as db:
            now=datetime.now(timezone.utc); end=now+timedelta(seconds=60)
            expired=d.rate_buckets.c.expires_at<=now
            stmt=d.dialect_insert(db.conn,d.rate_buckets).values(key='off-products-global',hits=1,expires_at=end)
            row=db.conn.execute(stmt.on_conflict_do_update(index_elements=['key'],
                set_={'hits':case((expired,1),else_=d.rate_buckets.c.hits+1),
                      'expires_at':case((expired,end),else_=d.rate_buckets.c.expires_at)},
                where=or_(expired,d.rate_buckets.c.hits<10)).returning(d.rate_buckets.c.key)).first()
            if not row:raise HTTPException(429,'外部食品库共享查询额度已满，请一分钟后再试')
        try:data=await fetch(barcode)
        except (httpx.HTTPError,ValueError):raise HTTPException(503,'外部食品库暂不可用，请稍后重试或手工添加') from None
        if not isinstance(data,dict):raise HTTPException(502,'外部食品库返回格式异常')
        if data.get('status') not in (1,'success') or not isinstance(data.get('product'),dict):raise HTTPException(404,'未找到该条码，请手工核对添加')
        food=normalize(data['product'],barcode)
        candidate={'food':food,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),
            'fetched_at':datetime.now(timezone.utc).isoformat(),'requires_confirmation':True}
        with connection() as db:db.write('external_food_candidate',barcode,candidate)
        return candidate
    @api.post('/{barcode}/confirm')
    def confirm(barcode:str,body:Confirm):
        check_barcode(barcode)
        with connection() as db:
            db.lock_user();candidate=db.read('external_food_candidate',barcode)
            if not candidate or datetime.fromisoformat(candidate['expires_at'])<datetime.now(timezone.utc):
                raise HTTPException(409,'请先重新查询并核对标签')
            food={**candidate['food'],'review_status':'user_confirmed_label'}
            db.write('external_food',food['id'],{**food,'confirmed_at':datetime.now(timezone.utc).isoformat()})
            return {'food':food,'message':'已保存到本人食物库，尚未记录任何饮食'}
    return api
