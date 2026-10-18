"""Local MVP. Single local user; add authentication before any public deployment."""
import json
import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('FIT_DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'fitness.db'

@contextmanager
def connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()

with connection() as db:
    db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, payload TEXT)')

def save(kind, payload, key=None):
    key = key or str(uuid4())
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO records VALUES (?, ?, ?)', (key, kind, json.dumps(payload, ensure_ascii=False)))
    return {'id': key, **payload}

def records(kind):
    with connection() as db:
        rows = db.execute('SELECT id, payload FROM records WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
    return [{'id': row['id'], **json.loads(row['payload'])} for row in rows]

app = FastAPI(title='LiftLab API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origin_regex=r'https?://(localhost|127\.0\.0\.1)(:\d+)?',
                   allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type'])

EXERCISES = [
    {'id': 'bench', 'name': '平板杠铃卧推', 'type': 'weighted', 'view': '固定侧面，完整覆盖杠铃和上身；录像时保持保护措施。'},
    {'id': 'squat', 'name': '高杠杠铃深蹲', 'type': 'weighted', 'view': '固定侧面，完整覆盖全身和杠铃，避免器械遮挡。'},
    {'id': 'deadlift', 'name': '传统杠铃硬拉', 'type': 'weighted', 'view': '固定侧面，覆盖全身、杠铃和地面，穿便于观察的衣服。'},
]
# Curated starter examples, per 100 g; not a comprehensive licensed food database.
FOODS = [
    {'id': 'rice', 'name': '熟米饭', 'kcal': 116, 'protein': 2.6, 'carbs': 25.9, 'fat': 0.3},
    {'id': 'chicken', 'name': '熟鸡胸肉（无皮，示例）', 'kcal': 165, 'protein': 31, 'carbs': 0, 'fat': 3.6},
    {'id': 'egg', 'name': '水煮鸡蛋（可食部分）', 'kcal': 155, 'protein': 12.6, 'carbs': 1.1, 'fat': 10.6},
    {'id': 'broccoli', 'name': '熟西兰花（示例）', 'kcal': 35, 'protein': 2.4, 'carbs': 7.2, 'fat': 0.4},
]

class Profile(BaseModel):
    age: int = Field(ge=18, le=90)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=250)
    sex: Literal['male', 'female']
    goal: Literal['fat_loss', 'muscle_gain']
    experience: Literal['beginner', 'intermediate'] = 'beginner'
    days: int = Field(ge=2, le=3)
    restrictions: str = Field(default='', max_length=1000)

class Meal(BaseModel):
    food_id: str
    grams: float = Field(gt=0, le=3000)
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack'] = 'breakfast'
    day: date | None = None

def nutrition_today():
    return datetime.now(timezone(timedelta(hours=8))).date()

NUTRIENTS = ['kcal', 'protein', 'fat', 'carbs']
MEAL_LABELS = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '加餐', 'unassigned': '未分类'}

def nutrient_totals(items):
    return {k: float(sum((Decimal(str(item['nutrients'][k])) for item in items), Decimal(0)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) for k in NUTRIENTS}

class Training(BaseModel):
    exercise_id: str
    weight_kg: float = Field(ge=0, le=500)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    rpe: float = Field(ge=1, le=10)
    pain: bool = False
    day: date = Field(default_factory=date.today)

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'local_single_user', 'vision_enabled': False}

@app.get('/api/catalog')
def catalog():
    return {'exercises': EXERCISES, 'foods': FOODS, 'food_source': 'MVP 示例数据，每100克；仅用于验证记录流程'}

@app.get('/api/profile')
def get_profile():
    items = records('profile')
    return items[0] if items else None

@app.put('/api/profile')
def put_profile(profile: Profile):
    return save('profile', profile.model_dump(), 'local-profile')

@app.post('/api/plans')
def generate_plan():
    profile = get_profile()
    if not profile:
        raise HTTPException(409, '请先保存用户画像')
    if profile['restrictions'].strip():
        raise HTTPException(409, '你填写了伤病或训练限制，当前模板需要教练审核后才能生成。')
    # Conservative starter template. No automatic load prescription.
    days = []
    for i in range(profile['days']):
        days.append({'name': f'训练日 {i+1}', 'rest_note': '训练日之间至少安排一个休息日', 'exercises': [
            {'exercise_id': e['id'], 'name': e['name'], 'sets': 2 if e['id'] == 'deadlift' else 3,
             'reps': '5', 'rest_seconds': 180, 'load': '选择可控重量，保留约3次余力'} for e in EXERCISES]})
    bmr = 10 * profile['weight_kg'] + 6.25 * profile['height_cm'] - 5 * profile['age'] + (5 if profile['sex'] == 'male' else -161)
    kcal = round(bmr * 1.4 + (-250 if profile['goal'] == 'fat_loss' else 200))
    protein = round(profile['weight_kg'] * 1.6)
    fat = round(profile['weight_kg'] * 0.8)
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return save('plan', {'created_on': date.today().isoformat(), 'profile_snapshot': profile,
        'rule_version': 'starter-0.1', 'status': 'starter_template', 'days': days,
        'nutrition': {'kcal': kcal, 'protein': protein, 'fat': fat, 'carbs': carbs},
        'note': '起始模板与估算目标，尚未经专业审核；根据执行与体重趋势复核。活动系数暂设1.4。'})

@app.get('/api/plans')
def get_plans():
    return records('plan')

@app.post('/api/meals')
def add_meal(meal: Meal):
    today = nutrition_today()
    if meal.day is not None and meal.day != today:
        raise HTTPException(422, '饮食仅支持记录当天，请刷新页面后重试')
    food = next((f for f in FOODS if f['id'] == meal.food_id), None)
    if not food:
        raise HTTPException(422, '食物不存在')
    return save('meal', {**meal.model_dump(mode='json'), 'day': today.isoformat(), 'name': food['name'],
        'nutrients': {k: float((Decimal(str(food[k])) * Decimal(str(meal.grams)) / 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) for k in ['kcal', 'protein', 'fat', 'carbs']},
        'source': 'starter-example-v1'})

@app.get('/api/meals')
def get_meals():
    today = nutrition_today().isoformat()
    return [item for item in records('meal') if item['day'] == today]

@app.get('/api/nutrition/today')
def nutrition_summary():
    today = nutrition_today().isoformat()
    items = [item for item in records('meal') if item['day'] == today]
    totals = nutrient_totals(items)
    groups = []
    for kind, label in MEAL_LABELS.items():
        entries = [item for item in items if item.get('meal_type', 'unassigned') == kind]
        if kind == 'unassigned' and not entries:
            continue
        groups.append({'meal_type': kind, 'label': label, 'items': entries, 'totals': nutrient_totals(entries)})
    plans = records('plan')
    profile = get_profile()
    current = plans[0] if plans else None
    target_status = 'missing'
    target = None
    if current and profile:
        if current['profile_snapshot'] == profile:
            target = current['nutrition']
            target_status = 'ready'
        else:
            target_status = 'stale'
    comparisons = {}
    for key in NUTRIENTS:
        goal = target[key] if target else None
        delta = round(totals[key] - goal, 1) if goal is not None else None
        comparisons[key] = {'consumed': totals[key], 'target': goal,
            'remaining': max(0, -delta) if delta is not None else None,
            'excess': max(0, delta) if delta is not None else None,
            'percent': round(totals[key] / goal * 100, 1) if goal and goal > 0 else None}
    return {'day': today, 'timezone': 'Asia/Shanghai', 'records': items, 'groups': groups,
            'totals': totals, 'target': target, 'target_status': target_status, 'comparison': comparisons}

@app.delete('/api/meals/{record_id}')
def delete_meal(record_id: str):
    with connection() as db:
        existing = db.execute('SELECT payload FROM records WHERE id=? AND kind=?', (record_id, 'meal')).fetchone()
        if not existing:
            raise HTTPException(404, '记录不存在')
        if json.loads(existing['payload'])['day'] != nutrition_today().isoformat():
            raise HTTPException(422, '该记录不属于当天，请刷新当天饮食')
        result = db.execute('DELETE FROM records WHERE id=? AND kind=?', (record_id, 'meal'))
    if not result.rowcount:
        raise HTTPException(404, '记录不存在')
    return {'deleted': True}

@app.post('/api/training')
def add_training(training: Training):
    if training.exercise_id not in [e['id'] for e in EXERCISES]:
        raise HTTPException(422, '动作不存在')
    return save('training', {**training.model_dump(mode='json'),
        'feedback': '记录到不适，请停止自动加重并寻求专业评估。' if training.pain else '已记录；当前版本不会自动增加重量。'})

@app.get('/api/training')
def get_training():
    return records('training')

@app.post('/api/media')
async def upload_media(kind: Literal['meal', 'video'] = Form(...), exercise_id: str = Form(''), file: UploadFile = File(...)):
    if kind == 'video' and exercise_id not in [e['id'] for e in EXERCISES]:
        raise HTTPException(422, '请选择支持的动作')
    allowed = {'meal': {'image/jpeg': '.jpg', 'image/png': '.png'},
               'video': {'video/mp4': '.mp4', 'video/quicktime': '.mov'}}
    suffix = allowed[kind].get(file.content_type)
    if not suffix:
        raise HTTPException(415, '支持 JPG/PNG 图片或 MP4/MOV 视频')
    limit = (10 if kind == 'meal' else 100) * 1024 * 1024
    media_dir = DATA / 'uploads'
    media_dir.mkdir(exist_ok=True)
    key = str(uuid4())
    target = media_dir / (key + suffix)
    size = 0
    try:
        with target.open('wb') as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, '文件超过大小限制')
                stream.write(chunk)
        if not size:
            raise HTTPException(422, '文件为空')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return save('media', {'kind': kind, 'exercise_id': exercise_id, 'bytes': size,
        'status': 'awaiting_integration', 'message': '文件已保存。识别模型尚未接入，未生成分析结果。',
        'stored_name': target.name}, key)

@app.get('/api/media')
def get_media():
    return records('media')

flutter_web = ROOT / 'mobile' / 'build' / 'web'
if flutter_web.exists():
    app.mount('/app', StaticFiles(directory=flutter_web, html=True), name='flutter')
app.mount('/', StaticFiles(directory=ROOT / 'preview', html=True), name='preview')
