import importlib
import os
import sys
import tempfile
from pathlib import Path
from datetime import date
import pytest

from fastapi.testclient import TestClient

temp = tempfile.TemporaryDirectory()
os.environ['FIT_DATA_DIR'] = temp.name
sys.path.insert(0, str(Path(__file__).parent))
module = importlib.import_module('app')
client = TestClient(module.app)
PROFILE = {'age': 28, 'height_cm': 175, 'weight_kg': 70, 'sex': 'male',
           'goal': 'muscle_gain', 'experience': 'beginner', 'days': 3}
PLAN = {'name': '我的周计划', 'days': [{'name': '周一', 'exercises': [
    {'exercise_id': 'bench', 'weight_kg': 75, 'sets': 4, 'reps': 5, 'rest_seconds': 150}]}]}

@pytest.fixture(autouse=True)
def isolate_records():
    with module.connection() as db:
        db.execute('DELETE FROM records')
        db.execute('DELETE FROM catalog_items')
    module.library.initialize(module.connection)

def test_coach_partial_profile_complete_sync_and_retry(monkeypatch):
    replies = []
    async def fake(message, history, profile, context):
        replies.append((message, history, profile, context))
        if not history:
            return {'reply': '了解，你希望优先增肌。每周可以训练几天？', 'profile_updates': [
                {'field': 'age', 'value': 28, 'evidence': '28岁'},
                {'field': 'goal', 'value': 'muscle_gain', 'evidence': '想增肌'}]}, 'test-model'
        return {'reply': '资料已足够制定草稿，可以到训练计划页生成。', 'profile_updates': [
            {'field': 'height_cm', 'value': 175, 'evidence': '175cm'},
            {'field': 'weight_kg', 'value': 70, 'evidence': '70kg'},
            {'field': 'sex', 'value': 'male', 'evidence': '男性'},
            {'field': 'experience', 'value': 'beginner', 'evidence': '刚开始训练'},
            {'field': 'days', 'value': 3, 'evidence': '每周3天'},
            {'field': 'dietary_preferences', 'value': '不喝牛奶', 'evidence': '不喝牛奶'}]}, 'test-model'
    monkeypatch.setattr(module.coach, 'respond', fake)
    first = {'request_id': 'request-0001', 'message': '我28岁，想增肌'}
    result = client.post('/api/coach/messages', json=first)
    assert result.status_code == 200
    assert result.json()['profile']['facts'] == {'age': 28, 'goal': 'muscle_gain'}
    assert not result.json()['profile']['complete']
    assert client.get('/api/profile').json() is None
    assert client.get('/api/nutrition/today').json()['target_status'] == 'missing'
    assert client.post('/api/coach/messages', json=first).status_code == 200
    assert len(replies) == 1  # Retry does not bill another request or duplicate the turn.
    assert client.post('/api/coach/messages', json={**first, 'message': '其他消息'}).status_code == 409
    second = {'request_id': 'request-0002',
              'message': '我175cm、70kg，男性，刚开始训练，每周3天，不喝牛奶'}
    assert client.post('/api/coach/messages', json=second).json()['profile']['complete']
    profile = client.get('/api/profile').json()
    assert profile['age'] == 28 and profile['weight_kg'] == 70 and profile['days'] == 3
    assert client.get('/api/nutrition/today').json()['target_status'] == 'ready'
    assert len(client.get('/api/coach/messages').json()['turns']) == 2
    assert replies[1][2]['age'] == 28 and len(replies[1][1]) == 1
    assert replies[0][3]['video_evidence_available'] is False
    assert client.patch('/api/coach/profile', json={'weight_kg': 72}).status_code == 200
    assert client.get('/api/profile').json()['weight_kg'] == 72
    assert client.get('/api/coach/profile').json()['facts']['dietary_preferences'] == '不喝牛奶'
    client.put('/api/profile', json={**PROFILE, 'weight_kg': 74})
    assert client.get('/api/coach/profile').json()['facts']['weight_kg'] == 74

@pytest.mark.parametrize('update', [
    {'field': 'age', 'value': 28, 'evidence': '历史消息28岁'},
    {'field': 'age', 'value': 12, 'evidence': '28岁'},
    {'field': 'age', 'value': 50, 'evidence': '28岁'},
    {'field': 'unknown', 'value': 'test', 'evidence': '28岁'},
    {'field': 'days', 'value': True, 'evidence': '28岁'},
])
def test_coach_invalid_extraction_does_not_save_anything(monkeypatch, update):
    async def fake(*args):
        return {'reply': '回复', 'profile_updates': [update]}, 'test-model'
    monkeypatch.setattr(module.coach, 'respond', fake)
    result = client.post('/api/coach/messages', json={'request_id': 'invalid-0001', 'message': '我28岁'})
    assert result.status_code == 502
    assert client.get('/api/coach/profile').json()['facts'] == {}
    assert client.get('/api/coach/messages').json()['turns'] == []

def test_coach_does_not_overwrite_profile_changed_while_waiting(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    async def fake(*args):
        module.put_profile(module.Profile(**{**PROFILE, 'weight_kg': 73}))
        return {'reply': '回复', 'profile_updates': [
            {'field': 'weight_kg', 'value': 72, 'evidence': '72kg'}]}, 'test-model'
    monkeypatch.setattr(module.coach, 'respond', fake)
    assert client.post('/api/coach/messages', json={
        'request_id': 'conflict-0001', 'message': '我72kg'}).status_code == 409
    assert client.get('/api/profile').json()['weight_kg'] == 73
    assert client.get('/api/coach/messages').json()['turns'] == []

def test_plan_uses_coach_preferences_and_rejects_changed_preferences(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    client.patch('/api/coach/profile', json={'equipment': '健身房器械', 'schedule': '晚上训练'})
    async def fake(profile, *args):
        assert profile['equipment'] == '健身房器械' and profile['schedule'] == '晚上训练'
        return ai_result(), 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    response = client.post('/api/plans/generate')
    assert response.status_code == 200
    draft = response.json()
    client.patch('/api/coach/profile', json={'equipment': '只有哑铃'})
    assert client.post('/api/plans', json={
        k: draft[k] for k in ('name', 'days', 'generation_id')}).status_code == 409

def test_coach_provider_sends_prompt_context_and_explicit_errors(monkeypatch):
    import httpx
    config = {'AI_API_KEY': 'test-secret', 'AI_BASE_URL': 'https://model.example/v1', 'AI_MODEL': 'test-model'}
    monkeypatch.setattr(module.ai_planner, 'settings', lambda: config)
    def handler(request):
        body = __import__('json').loads(request.content)
        assert request.headers['Authorization'] == 'Bearer test-secret'
        assert 'AI 健身教练' in body['messages'][0]['content']
        assert body['messages'][-1] == {'role': 'user', 'content': '如何找到深蹲动作库？'}
        assert '蹲：髋膝屈伸' in body['messages'][1]['content']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content':
            __import__('json').dumps({'reply': '打开侧边栏 AI 陪训中的动作库。', 'profile_updates': []})}}]})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(module.ai_planner.httpx, 'AsyncClient',
                        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    result = client.post('/api/coach/messages', json={
        'request_id': 'provider-0001', 'message': '如何找到深蹲动作库？'})
    assert result.status_code == 200 and result.json()['profile_changes'] == []
    assert 'test-secret' not in result.text
    assert client.get('/api/coach/profile').json()['facts'] == {}
    assert 'AI 健身教练' in client.get('/api/coach/prompt').json()['prompt']
    monkeypatch.setattr(module.ai_planner, 'settings', lambda: {k: '' for k in config})
    assert not client.get('/api/coach/status').json()['configured']
    assert client.post('/api/coach/messages', json={
        'request_id': 'provider-0002', 'message': '你好'}).status_code == 503
    assert len(client.get('/api/coach/messages').json()['turns']) == 1

def test_library_search_categories_and_sources():
    assert len(client.get('/api/catalog').json()['exercises']) == 3
    assert len(client.get('/api/catalog?extended=true').json()['exercises']) == 38
    result = client.get('/api/library/foods?q=香蕉').json()
    assert result['total'] == 1
    assert result['items'][0]['source_id'] == '173944'
    assert result['items'][0]['basis_g'] == 100
    assert result['items'][0]['kcal'] == 89
    assert client.get('/api/library/foods?limit=1').json()['total'] == 44
    assert len(client.get('/api/library/foods?limit=1').json()['items']) == 1
    assert client.get('/api/library/exercises?type=weighted').json()['total'] == 31
    assert client.get('/api/library/exercises?type=bodyweight').json()['total'] == 7
    assert client.get('/api/library/exercises?q=哑铃&category=背部').json()['items'][0]['id'] == 'dumbbell_row'

CUSTOM_FOOD = {'name':'测试酸奶','category':'乳制品','state':'prepared',
    'kcal':100,'protein':8,'fat':4,'carbs':8,'source_label':'测试包装每100g标签'}

def test_library_edits_do_not_recalculate_old_meals_and_archive_is_durable():
    entry = client.post('/api/library/foods',json=CUSTOM_FOOD).json()
    meal = client.post('/api/meals',json={'food_id':entry['id'],'grams':150}).json()
    assert meal['nutrients']['kcal'] == 150
    assert meal['food_source'] == CUSTOM_FOOD['source_label']
    updated = client.put('/api/library/foods/'+entry['id'],json={**CUSTOM_FOOD,'kcal':120})
    assert updated.status_code == 200
    assert client.get('/api/meals').json()[0]['nutrients']['kcal'] == 150
    assert client.post('/api/meals',json={'food_id':entry['id'],'grams':100}).json()['nutrients']['kcal'] == 120
    assert client.delete('/api/library/foods/'+entry['id']).status_code == 200
    assert client.post('/api/meals',json={'food_id':entry['id'],'grams':100}).status_code == 422
    assert len(client.get('/api/meals').json()) == 2
    client.delete('/api/library/foods/rice')
    module.library.initialize(module.connection)
    assert client.get('/api/library/foods/rice').status_code == 404

def test_library_import_is_atomic_and_limits_nutrients():
    first={**CUSTOM_FOOD,'id':'import_a'}
    invalid={**CUSTOM_FOOD,'id':'import_b','protein':90,'fat':90}
    assert client.post('/api/library/foods/import',json=[first,invalid]).status_code == 422
    assert client.get('/api/library/foods/import_a').status_code == 404
    assert client.post('/api/library/foods/import',json=[first,{**CUSTOM_FOOD,'id':'rice'}]).status_code == 409
    assert client.get('/api/library/foods/import_a').status_code == 404
    assert client.post('/api/library/foods/import',json=[first]).json()['imported'] == 1
    assert client.get('/api/library/foods/export').json()['kind'] == 'foods'
    assert client.post('/api/library/foods',json={**CUSTOM_FOOD,'kcal':-10}).status_code == 422

def test_more_weighted_exercises_work_in_plan_training_and_rm():
    entry=client.post('/api/library/exercises',json={'name':'测试划船','category':'背部',
        'equipment':'器械','realtime_supported':True}).json()
    assert entry['realtime_supported'] is False
    assert client.put('/api/library/exercises/'+entry['id'],json={**entry,'equipment':'另一器械'}).status_code == 422
    assert client.post('/api/training',json={'exercise_id':entry['id'],'weight_kg':20,'sets':3,'reps':8,'rpe':7}).status_code == 200
    assert client.post('/api/rm',json={'exercise_id':entry['id'],'weight_kg':20,'reps':8,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True}).status_code == 200
    plan={'name':'扩展计划','days':[{'name':'周一','exercises':[{**PLAN['days'][0]['exercises'][0],'exercise_id':entry['id'],'weight_kg':10}]}]}
    assert client.post('/api/plans',json=plan).status_code == 200
    assert client.post('/api/training',json={'exercise_id':'pushup','weight_kg':0,'sets':3,'reps':8,'rpe':7}).status_code == 422
    plan['days'][0]['exercises'][0]['exercise_id']='unknown'
    assert client.post('/api/plans/assess',json=plan).status_code == 422
    assert client.put('/api/library/exercises/bench',json={'name':'不同卧推','category':'胸部','equipment':'哑铃'}).status_code == 422

def test_ai_uses_weighted_catalog_and_rejects_unknown_actions(monkeypatch):
    client.put('/api/profile',json=PROFILE)
    result=ai_result()
    async def fake(profile,rm,schema):
        assert 'dumbbell_row' in schema['$defs']['PlanExercise']['properties']['exercise_id']['enum']
        assert 'pushup' not in schema['$defs']['PlanExercise']['properties']['exercise_id']['enum']
        result['days'][0]['exercises'][0]['exercise_id']='pushup'
        return result,'test-model'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    assert client.post('/api/plans/generate').status_code == 502

def test_joint_classification_and_gif_assets():
    result=client.get('/api/library/exercises?category=肘屈曲&body_part=手臂').json()
    assert result['category_dimension']=='joint_movement'
    assert len(result['items'])==3
    assert '水平推' in result['categories']
    assert '胸部' in result['body_parts']
    assert client.get('/api/library/foods?category=乳制品').json()['category_dimension']=='food_type'
    from PIL import Image
    for entry in client.get('/api/catalog?extended=true').json()['exercises']:
        assert entry['joint_actions'] and entry['primary_muscles']
        assert entry['technique']['key_points']
        file=module.ROOT/'backend'/entry['demo']['url'].lstrip('/')
        with Image.open(file) as gif:
            assert gif.format=='GIF' and gif.n_frames>1
    assert client.get('/assets/exercise-demos/bench.gif').status_code==200

def test_reference_is_shared_with_prompts_and_edits_change_hash():
    payload={'name':'测试肘屈曲','category':'手臂','equipment':'哑铃',
        'movement_pattern':'肘屈曲','joint_actions':['肘屈伸'],'body_regions':['手臂'],
        'primary_muscles':['肱二头肌'],'secondary_muscles':['肱肌'],
        'technique':{'setup':['站稳'],'execution':['屈肘并控制返回'],'key_points':['不要摆动'],
            'common_errors':[{'id':'custom_swing','description':'观察躯干摆动','guidance':'站稳后复核'}]}}
    entry=client.post('/api/library/exercises',json=payload).json()
    before=client.get('/api/library/exercises/'+entry['id']+'/analysis-context').json()
    assert before['reference']['joint_actions']==entry['joint_actions']
    assert before['reference']['technique']==entry['technique']
    assert '膝超过脚尖' in before['system_prompt']
    payload['technique']['key_points']=['新的共同提示文案']
    assert client.put('/api/library/exercises/'+entry['id'],json=payload).status_code==200
    after=client.get('/api/library/exercises/'+entry['id']+'/analysis-context').json()
    assert after['reference_hash']!=before['reference_hash']
    assert after['reference']['technique']['key_points']==['新的共同提示文案']
    bench=module.library.find_entry(module.connection,'exercises','bench')
    context=module.library.exercise_content.analysis_context(bench,'front',2)
    assert 'bench_visible_control' in context['allowed_cue_ids']
    assert 'bench_bar_path' not in context['allowed_cue_ids']  # Unvalidated book candidate stays reference-only.
    changed={**bench,'technique':{**bench['technique'],'key_points':['更新的共同教学文案']}}
    update=client.put('/api/library/exercises/bench',json=changed)
    assert update.status_code==200
    assert update.json()['realtime_supported'] is True
    assert client.get('/api/library/exercises/bench/analysis-context').json()['reference']['technique']['key_points']==['更新的共同教学文案']

def test_visual_analysis_sends_shared_reference_and_rejects_wrong_evidence(monkeypatch):
    import base64, io, json, httpx
    from PIL import Image
    stream=io.BytesIO();Image.new('RGB',(32,32),'white').save(stream,format='JPEG')
    frame={'mime_type':'image/jpeg','image_base64':base64.b64encode(stream.getvalue()).decode()}
    config={'VISION_API_KEY':'test-secret','VISION_BASE_URL':'https://example.com/v1','VISION_MODEL':'test-vision'}
    monkeypatch.setattr(module.movement_analysis,'settings',lambda:config)
    observed=[]
    result={'status':'observations','summary':'疑似观察，建议复核','observations':[{
        'cue_id':'bench_visible_control','evidence':'截图中的左右位置疑似不一致',
        'frame_indices':[0,1],'confidence':'medium'}]}
    def handler(request):
        body=json.loads(request.content)
        reference=json.loads(body['messages'][1]['content'][0]['text'])['analysis_context']['reference']
        observed.append(reference)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]})
    original_client=httpx.AsyncClient
    monkeypatch.setattr(module.movement_analysis.httpx,'AsyncClient',lambda **kwargs:original_client(transport=httpx.MockTransport(handler),**kwargs))
    request={'exercise_id':'bench','camera_view':'front','frames':[frame,frame]}
    response=client.post('/api/movement/analyze',json=request)
    assert response.status_code==200
    assert observed[0]['primary_muscles']==['胸大肌']
    assert observed[0]['movement_pattern']=='水平推'
    assert response.json()['reference']==observed[0]
    assert response.json()['observations'][0]['guidance']==observed[0]['technique']['common_errors'][0]['guidance']
    assert 'image_base64' not in json.dumps(module.records('movement_analysis'))
    result['observations'][0]['frame_indices']=[99]
    assert client.post('/api/movement/analyze',json=request).status_code==502
    result['observations'][0]['frame_indices']=[0]
    result['observations'][0]['cue_id']='squat_visible_control'
    assert client.post('/api/movement/analyze',json=request).status_code==502
    assert len(module.records('movement_analysis'))==1
    invalid={**frame,'image_base64':base64.b64encode(b'not an image').decode()}
    assert client.post('/api/movement/analyze',json={**request,'frames':[invalid,invalid]}).status_code==422
    assert client.post('/api/movement/analyze',json={**request,'camera_view':'side'}).json()['status']=='insufficient_evidence'

def test_user_plan_is_preserved_and_versioned():
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    first = client.post('/api/plans', json=PLAN).json()
    second = client.post('/api/plans', json=PLAN).json()
    assert first['id'] != second['id']
    assert len(first['days']) == 1
    assert first['days'][0]['exercises'][0]['weight_kg'] == 75
    assert first['days'][0]['exercises'][0]['sets'] == 4
    assert first['days'][0]['exercises'][0]['rest_seconds'] == 150
    assert first['source'] == 'user'
    assert first['assessment']['items'][0]['status'] == 'missing_rm'
    assert client.post('/api/plans').status_code == 422  # No automatic generation.

def test_restrictions_require_review_but_keep_user_plan():
    client.put('/api/profile', json={**PROFILE, 'restrictions': '肩部疼痛'})
    result = client.post('/api/plans', json=PLAN)
    assert result.status_code == 200
    assert result.json()['assessment']['items'][0]['status'] == 'review_required'
    client.put('/api/profile', json=PROFILE)

def test_nutrients_and_delete():
    response = client.post('/api/meals', json={'food_id': 'rice', 'grams': 150})
    meal = response.json()
    assert meal['nutrients']['kcal'] == 174
    assert meal['nutrients']['carbs'] == 38.9
    assert client.delete('/api/meals/' + meal['id']).status_code == 200
    assert client.delete('/api/meals/' + meal['id']).status_code == 404
    assert client.post('/api/meals', json={'food_id': 'unknown', 'grams': 150}).status_code == 422
    assert client.post('/api/meals', json={'food_id': 'rice', 'grams': -1}).status_code == 422

def test_pain_does_not_prescribe_more_load():
    response = client.post('/api/training', json={'exercise_id': 'bench', 'weight_kg': 20,
        'sets': 3, 'reps': 5, 'rpe': 7, 'pain': True})
    assert response.status_code == 200
    assert '停止自动加重' in response.json()['feedback']

def test_media_is_pending_not_fake_analysis():
    result = client.post('/api/media', data={'kind': 'video', 'exercise_id': 'squat'},
                         files={'file': ('test.mp4', b'local-test', 'video/mp4')})
    assert result.status_code == 200
    assert result.json()['status'] == 'awaiting_integration'
    assert 'score' not in result.json()
    assert (Path(temp.name) / 'uploads' / result.json()['stored_name']).exists()

def test_reject_empty_and_wrong_media_type():
    assert client.post('/api/media', data={'kind': 'meal'},
        files={'file': ('empty.jpg', b'', 'image/jpeg')}).status_code == 422
    assert client.post('/api/media', data={'kind': 'meal'},
        files={'file': ('bad.txt', b'bad', 'text/plain')}).status_code == 415
    assert client.post('/api/media', data={'kind': 'video', 'exercise_id': 'unknown'},
        files={'file': ('test.mp4', b'local-test', 'video/mp4')}).status_code == 422

def test_validation_and_preview():
    assert client.put('/api/profile', json={**PROFILE, 'age': 12}).status_code == 422
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['vision_enabled'] is False

def test_today_meal_groups_and_target_comparison():
    client.put('/api/profile', json=PROFILE)
    target = module.nutrition_target(PROFILE)
    client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'meal_type': 'breakfast'})
    client.post('/api/meals', json={'food_id': 'egg', 'grams': 100, 'meal_type': 'breakfast'})
    client.post('/api/meals', json={'food_id': 'chicken', 'grams': 100, 'meal_type': 'lunch'})
    summary = client.get('/api/nutrition/today').json()
    assert summary['totals'] == {'kcal': 494.0, 'protein': 47.5, 'fat': 14.7, 'carbs': 40.0}
    assert summary['groups'][0]['totals']['kcal'] == 329
    assert summary['groups'][1]['totals']['kcal'] == 165
    assert summary['target'] == target
    assert summary['comparison']['protein']['remaining'] == 64.5
    assert summary['comparison']['kcal']['excess'] == 0

def test_rollover_excludes_old_food_and_rejects_backdating(monkeypatch):
    monkeypatch.setattr(module, 'nutrition_today', lambda: date(2026, 10, 10))
    previous = client.post('/api/meals', json={'food_id': 'rice', 'grams': 150}).json()
    assert len(client.get('/api/meals').json()) == 1
    monkeypatch.setattr(module, 'nutrition_today', lambda: date(2026, 10, 11))
    assert client.get('/api/meals').json() == []
    summary = client.get('/api/nutrition/today').json()
    assert summary['totals']['kcal'] == 0
    assert summary['day'] == '2026-10-11'
    assert client.delete('/api/meals/' + previous['id']).status_code == 422
    assert client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'day': '2026-10-10'}).status_code == 422
    assert client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'day': '2026-10-12'}).status_code == 422
    assert len(module.records('meal')) == 1  # History retained; not included in today's totals.

def test_excess_and_delete_recalculates_totals():
    client.put('/api/profile', json=PROFILE)
    meal = client.post('/api/meals', json={'food_id': 'rice', 'grams': 3000, 'meal_type': 'dinner'}).json()
    comparison = client.get('/api/nutrition/today').json()['comparison']['kcal']
    assert comparison['excess'] > 0
    assert comparison['remaining'] == 0
    assert comparison['percent'] > 100
    client.delete('/api/meals/' + meal['id'])
    assert client.get('/api/nutrition/today').json()['totals']['kcal'] == 0

def test_nutrition_targets_update_without_a_training_plan():
    assert client.get('/api/nutrition/today').json()['target_status'] == 'missing'
    client.put('/api/profile', json=PROFILE)
    assert client.get('/api/nutrition/today').json()['target']['protein'] == 112
    client.put('/api/profile', json={**PROFILE, 'weight_kg': 75})
    summary = client.get('/api/nutrition/today').json()
    assert summary['target_status'] == 'ready'
    assert summary['target']['protein'] == 120
    assert client.get('/api/plans').json() == []

def test_rm_reference_and_draft_assessment_do_not_change_plan():
    rm = client.post('/api/rm', json={'exercise_id':'bench','weight_kg':87,'reps':5,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True}).json()
    assert rm['reference_1rm_kg'] == 100
    result = client.post('/api/plans/assess', json=PLAN).json()
    assert result['items'][0]['load_percent'] == 75
    assert result['items'][0]['reference_1rm_kg'] == 100
    assert result['items'][0]['status'] == 'reference_only'
    assert client.get('/api/plans').json() == []
    saved = client.post('/api/plans', json=PLAN).json()
    assert saved['days'][0]['exercises'][0]['weight_kg'] == 75

def test_rm_evaluation_flags_high_load_and_rejects_unsupported_rm():
    from copy import deepcopy
    client.post('/api/rm',json={'exercise_id':'bench','weight_kg':100,'reps':1,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True})
    plan = deepcopy(PLAN)
    plan['days'][0]['exercises'][0]['weight_kg'] = 95
    assert client.post('/api/plans/assess',json=plan).json()['items'][0]['status'] == 'high_relative_load'
    plan['days'][0]['exercises'][0]['weight_kg'] = 105
    assert client.post('/api/plans/assess',json=plan).json()['items'][0]['status'] == 'above_reference'
    assert client.post('/api/rm',json={'exercise_id':'bench','weight_kg':80,'reps':11,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True}).status_code == 422

def test_rm_expiry_future_dates_and_nonmaximum_sets(monkeypatch):
    monkeypatch.setattr(module,'nutrition_today',lambda:date(2026,10,11))
    fields={'exercise_id':'bench','weight_kg':100,'reps':1,'confirmed_maximum':True}
    assert client.post('/api/rm',json={**fields,'measured_on':'2026-10-12'}).status_code == 422
    client.post('/api/rm',json={**fields,'measured_on':'2026-06-01'})
    assert client.post('/api/plans/assess',json=PLAN).json()['items'][0]['status'] == 'stale_rm'
    client.post('/api/rm',json={**fields,'measured_on':'2026-10-11','confirmed_maximum':False})
    assert client.post('/api/plans/assess',json=PLAN).json()['items'][0]['status'] == 'missing_rm'

def test_rm_is_matched_by_variant_and_measurement_date(monkeypatch):
    monkeypatch.setattr(module,'nutrition_today',lambda:date(2026,10,11))
    fields={'exercise_id':'bench','reps':1,'confirmed_maximum':True}
    client.post('/api/rm',json={**fields,'weight_kg':100,'measured_on':'2026-10-10'})
    client.post('/api/rm',json={**fields,'weight_kg':80,'measured_on':'2026-10-01'})
    assert client.get('/api/rm').json()[0]['weight_kg'] == 100
    plan={'name':'深蹲','days':[{'name':'周二','exercises':[{**PLAN['days'][0]['exercises'][0],'exercise_id':'squat'}]}]}
    assert client.post('/api/plans/assess',json=plan).json()['items'][0]['status'] == 'missing_rm'

def test_old_generated_templates_are_not_active_user_plans():
    module.save('plan',{'status':'starter_template','days':[]})
    assert client.get('/api/plans').json() == []

def test_legacy_meals_are_not_silently_assigned_to_breakfast():
    module.save('meal', {'day': module.nutrition_today().isoformat(), 'name': '旧记录',
        'nutrients': {'kcal': 100, 'protein': 10, 'fat': 2, 'carbs': 10}})
    summary = client.get('/api/nutrition/today').json()
    assert summary['groups'][-1]['meal_type'] == 'unassigned'
    assert summary['totals']['kcal'] == 100

def ai_result():
    return {'name': 'AI周计划', 'days': [{'name': f'训练日{i + 1}',
        'exercises': [{**PLAN['days'][0]['exercises'][0], 'weight_kg': None}]} for i in range(3)],
        'rationale': '根据增肌目标安排', 'warmup': '逐步热身',
        'recovery': '训练日之间恢复', 'progression': '根据完成情况复核'}

def test_ai_generation_is_a_draft_and_preserves_provenance(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    async def fake(profile, rm, schema):
        assert profile['goal'] == 'muscle_gain'
        assert rm == {}
        return ai_result(), 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    result = client.post('/api/plans/generate', json={})
    assert result.status_code == 200
    draft = result.json()
    assert client.get('/api/plans').json() == []
    assert draft['assessment']['items'][0]['status'] == 'missing_load'
    saved = client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')})
    assert saved.status_code == 200
    assert saved.json()['source'] == 'ai'
    assert saved.json()['model'] == 'test-model'
    assert len(client.get('/api/plans').json()) == 1
    client.put('/api/profile', json={**PROFILE, 'weight_kg': 80})
    assert client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')}).status_code == 409

def test_ai_rejects_invalid_day_count_and_excessive_load(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    result = ai_result()
    async def fake(*args):
        return result, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    result['days'].pop()
    assert client.post('/api/plans/generate').status_code == 502
    result['days'].append({'name': '训练日3', 'exercises': [PLAN['days'][0]['exercises'][0].copy()]})
    client.post('/api/rm', json={'exercise_id': 'bench', 'weight_kg': 50, 'reps': 1,
        'measured_on': module.nutrition_today().isoformat(), 'confirmed_maximum': True})
    assert client.post('/api/plans/generate').status_code == 502
    assert module.records('plan_draft') == []

def test_ai_missing_config_is_explicit_and_secrets_not_exposed(monkeypatch):
    monkeypatch.setattr(module.ai_planner, 'settings', lambda: {'AI_API_KEY': '', 'AI_BASE_URL': '', 'AI_MODEL': ''})
    assert client.post('/api/plans/generate').status_code == 422
    client.put('/api/profile', json=PROFILE)
    assert client.post('/api/plans/generate').status_code == 503
    assert client.get('/api/ai/status').json()['configured'] is False
    monkeypatch.setattr(module.ai_planner, 'settings', lambda: {'AI_API_KEY': 'secret', 'AI_BASE_URL': 'https://example.com', 'AI_MODEL': 'test'})
    assert 'secret' not in client.get('/api/ai/status').text
