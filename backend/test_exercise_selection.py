"""Curation hides browsing noise without deleting old exercise identities."""
import json
import re
from pathlib import Path

from test_app import module, client, isolate_records, PLAN
from exercise_selection import selected_ids, visible


def test_every_selected_seed_has_a_real_demo_and_core_ids_survive():
    rows = module.library.all_entries(module.connection, 'exercises')
    selected = [r for r in rows if visible(r)]
    core = json.loads((module.ROOT / 'backend/data/exercises.json').read_text(encoding='utf-8'))
    assert len(selected) == 97
    assert {r['id'] for r in core} <= selected_ids()
    for row in selected:
        path = module.ROOT / 'backend' / row['demo']['url'].lstrip('/')
        assert path.is_file(), row['id']
    assert len(rows) == 1579  # Backing data remains complete.


def test_hidden_identity_is_still_usable_in_existing_plan_and_rm():
    hidden = 'ed_0038'
    assert hidden not in selected_ids()
    assert client.get('/api/library/exercises?q=' + hidden).json()['total'] == 0
    original = client.get('/api/library/exercises/' + hidden).json()
    assert original['id'] == hidden
    assert hidden not in {r['id'] for r in client.get('/api/catalog?extended=true').json()['exercises']}
    plan = json.loads(json.dumps(PLAN))
    plan['days'][0]['exercises'][0]['exercise_id'] = hidden
    saved = client.post('/api/plans', json=plan)
    assert saved.status_code == 200
    assert client.get('/api/plans').json()[0]['days'][0]['exercises'][0]['exercise_id'] == hidden
    assert hidden in {r['id'] for r in client.get('/api/catalog?extended=true').json()['exercises']}
    assert client.post('/api/rm', json={'exercise_id': hidden, 'weight_kg': 20, 'reps': 5,
        'measured_on': module.nutrition_today().isoformat(), 'confirmed_maximum': True}).status_code == 200
    assert client.get('/api/library/exercises/' + hidden).json() == original


def test_custom_entries_remain_visible_without_media_and_archives_stay_hidden():
    result = client.post('/api/library/exercises', json={'name': '我常用的划船',
        'category': '背部', 'equipment': '器械'}).json()
    assert result['id'] in {r['id'] for r in client.get('/api/library/exercises?q=我常用').json()['items']}
    assert client.delete('/api/library/exercises/bench').status_code == 200
    module.library.initialize(module.connection)
    assert client.get('/api/library/exercises/bench').status_code == 404
    assert len(module.library.all_entries(module.connection, 'foods')) == 44


def test_default_names_are_chinese_and_source_names_remain_searchable():
    rows = client.get('/api/library/exercises?limit=200').json()['items']
    assert len(rows) == 97
    assert all(not re.search('[A-Za-z]', row['name']) for row in rows)
    for query in ('死虫式', 'dead bug'):
        result = client.get('/api/library/exercises', params={'q': query}).json()
        assert result['items'][0]['id'] == 'ed_0276'
        assert result['items'][0]['name'] == '死虫式'
        assert result['items'][0]['original_name'] == 'dead bug'
    catalog = client.get('/api/catalog?extended=true').json()['exercises']
    assert all(not re.search('[A-Za-z]', row['name']) for row in catalog)
    assert client.get('/api/library/exercises/wg_skull_crusher').json()['name'] == '仰卧臂屈伸'


def test_localized_display_preserves_user_authored_names_and_stored_sources():
    with module.connection() as db:
        before = db.catalog_read('exercises', 'ed_0276')
        before = {**before, 'name': 'dead bug'}
        db.catalog_update('exercises', 'ed_0276', name='dead bug', payload=before)
    assert client.get('/api/library/exercises/ed_0276').json()['name'] == '死虫式'
    with module.connection() as db:
        assert db.catalog_read('exercises', 'ed_0276') == before
    from external_exercises import localize
    custom = {**before, 'source_kind': 'user', 'name': '我的Dead Bug'}
    assert localize(custom)['name'] == '我的Dead Bug'


def test_agent_exercise_search_returns_chinese_without_losing_english_lookup():
    import asyncio
    for query in ('死虫式', 'dead bug'):
        rows = asyncio.run(module.agent_service.tool('name-test', {}, {},
            'search_exercises', {'query': query}, 'name-call'))
        assert rows[0]['id'] == 'ed_0276'
        assert rows[0]['name'] == '死虫式'
