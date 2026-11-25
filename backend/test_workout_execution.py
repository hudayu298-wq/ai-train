"""Per-set server snapshots and exact-identity descriptive statistics."""
import json
from test_app import module, client, isolate_records, PLAN, workout_payload


def test_targets_survive_plan_edits_and_retry():
    plan = client.post('/api/plans', json=PLAN).json()
    body = workout_payload('snapshot-test-001', plan_id=plan['id'], plan_day='周一')
    body['exercises'][0]['sets'].insert(0, {'weight_kg':20,'reps':10,'rpe':3,'set_type':'warmup'})
    response = client.post('/api/workouts',json=body)
    assert response.status_code == 200
    record = response.json()
    comparison = record['summary']['target_comparison']
    assert comparison['planned_sets'] == 4
    assert comparison['recorded_planned_sets'] == 2
    assert comparison['sets'][0]['actual']['weight_kg'] == 40
    assert comparison['sets'][0]['target']['weight_kg'] == 75
    assert comparison['sets'][0]['delta']['weight_kg'] == -35
    assert comparison['sets'][2]['status'] == 'not_recorded'
    with module.connection() as db:
        saved = db.read('plan',plan['id'])
        saved['days'][0]['exercises'][0]['weight_kg'] = 90
        db.write('plan',plan['id'],saved)
    retried = client.post('/api/workouts',json=body).json()
    assert retried['summary']['target_comparison'] == comparison
    assert client.get('/api/workouts').json()['items'][0]['plan_snapshot']['days'][0]['exercises'][0]['weight_kg'] == 75
    assert client.get('/api/rm').json() == []


def test_no_plan_targets_are_invented_and_extra_sets_are_labelled():
    assert client.post('/api/workouts',json=workout_payload()).json()['summary']['target_comparison'] is None
    plan = json.loads(json.dumps(PLAN))
    plan['days'][0]['exercises'][0]['sets'] = 1
    plan['days'][0]['exercises'][0]['weight_kg'] = None
    saved = client.post('/api/plans',json=plan).json()
    body=workout_payload('unknown-target-01',plan_id=saved['id'],plan_day='周一')
    body['exercises'][0]['load_basis']='per_hand'
    comparison=client.post('/api/workouts',json=body).json()['summary']['target_comparison']
    assert comparison['sets'][0]['target']['weight_kg'] is None
    assert 'weight_kg' not in comparison['sets'][0]['delta']
    assert comparison['sets'][1]['status']=='extra_set'


def test_period_stats_separate_load_basis_and_owner():
    first=workout_payload('stats-identity-01')
    first['exercises'][0]['sets'].append({'weight_kg':20,'reps':10,'rpe':3,'set_type':'warmup'})
    assert client.post('/api/workouts',json=first).status_code == 200
    second=workout_payload('stats-identity-02')
    second['exercises'][0]['load_basis']='per_hand'
    second['exercises'][0]['equipment_id']='machine-A'
    assert client.post('/api/workouts',json=second).status_code == 200
    stats=client.get('/api/workouts').json()['training_memory']['last_28_days']
    assert stats['sessions']==2 and stats['training_days']==1
    assert stats['working_sets']==4
    assert len(stats['by_exercise'])==2
    assert all(g['volume_kg']==560 for g in stats['by_exercise'])
    with module.connection() as db:
        user=module.auth.new_user(db.conn,name='other stats owner')
    token=module.database.owner_context.set(user['id'])
    try:
        with module.connection() as db:
            assert module.workouts.memory(db)['last_28_days']['sessions']==0
    finally:
        module.database.owner_context.reset(token)


def test_stats_window_and_changed_load_basis_never_mix_weight_deltas():
    from datetime import timedelta
    rows = [{'day': (module.workouts.today() + timedelta(days=n)).isoformat(),
             'exercises': []} for n in (-28, -27, 0, 1)]
    assert module.workouts.period_stats(rows)['sessions'] == 2
    plan = client.post('/api/plans', json=PLAN).json()
    body = workout_payload('basis-target-001', plan_id=plan['id'], plan_day='周一')
    body['exercises'][0]['load_basis'] = 'per_hand'
    result = client.post('/api/workouts', json=body).json()['summary']['target_comparison']
    assert result['sets'][0]['target']['weight_kg'] == 75
    assert result['sets'][0]['weight_comparable'] is False
    assert 'weight_kg' not in result['sets'][0]['delta']
    assert result['sets'][0]['delta']['reps'] == 3
