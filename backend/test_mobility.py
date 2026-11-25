"""Manual pilot contracts: provenance, repeatability gates, history and owner isolation."""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import insert

sys.path.insert(0, str(Path(__file__).parent))
import database as d
import mobility as m


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    path=tmp_path/'mobility.db'
    engine=d.get_engine(path)
    d.metadata.create_all(engine)
    with engine.begin() as conn:
        for owner in ('owner-a','owner-b'):
            conn.execute(insert(d.users).values(id=owner,display_name=owner,active=True,role='user',created_at=d.now()))
    app=FastAPI()

    @app.middleware('http')
    async def owner_scope(request:Request, call_next):
        token=d.owner_context.set(request.headers.get('X-Test-Owner'))
        try:
            return await call_next(request)
        finally:
            d.owner_context.reset(token)
    app.include_router(m.router(lambda:d.connection(path)))
    with TestClient(app,headers={'X-Test-Owner':'owner-a'}) as test_client:
        yield test_client


def body(**changes):
    data={'request_id':'mobility-test-001','side':'left','observed_at':'2026-01-01T08:00:00+08:00',
        'conditions':{'surface':'same floor','ruler':'ruler-a','assessor':'self'},
        'practice_completed':True,'pain_score':0,
        'trials':[{'distance_cm':v,'heel_down':True,'knee_touched_wall':True,'knee_tracks_second_toe':True} for v in (8,8.1,8.2)]}
    return {**data,**changes}


def enabled(client):
    assert client.put('/api/mobility/settings',json={'storage_enabled':True}).status_code==200


def test_manual_contract_consent_and_idempotency(client):
    protocol=client.get('/api/mobility/protocol').json()
    assert protocol['capabilities']['camera_angle']=='unavailable_not_calibrated'
    assert '产品' in protocol['product_rules']['meaning']
    assert client.post('/api/mobility/measurements',json=body()).status_code==403
    enabled(client)
    first=client.post('/api/mobility/measurements',json=body())
    assert first.status_code==200
    item=first.json()
    assert item['mean_cm']==8.1 and item['spread_cm']==0.2 and item['comparable']
    assert item['source_method']=='manual_tape' and item['unit']=='cm'
    assert item['source']['id']=='konor-2012'
    assert client.post('/api/mobility/measurements',json=body()).json()['id']==item['id']
    assert client.post('/api/mobility/measurements',json=body(side='right')).status_code==409
    for change in ({'source_method':'camera_model'},{'protocol_version':'2'},{'mode':'passive'},
            {'unit':'degrees'},{'observed_at':'2026-01-01T08:00:00'},{'trials':[]},{'pain_score':True}):
        assert client.post('/api/mobility/measurements',json=body(**change)).status_code==422
    false_precision=body(request_id='precision-001')
    false_precision['trials'][0]['distance_cm']=8.123
    assert client.post('/api/mobility/measurements',json=false_precision).status_code==422


def test_pain_stops_and_bad_trials_never_enter_personal_trend(client):
    enabled(client)
    assert client.post('/api/mobility/measurements',json=body(pain_score=1)).status_code==422
    stop=client.post('/api/mobility/measurements',json=body(pain_score=2,pain_location='踝前',stopped_due_to_pain=True,trials=[]))
    assert stop.status_code==200 and stop.json()['mean_cm'] is None and not stop.json()['comparable']
    poor=body(request_id='mobility-test-002')
    poor['trials'][2]['distance_cm']=11
    saved=client.post('/api/mobility/measurements',json=poor).json()
    assert not saved['comparable'] and '产品' in saved['quality_notes'][-1]
    poor=body(request_id='mobility-test-003')
    poor['trials'][0]['heel_down']=False
    assert not client.post('/api/mobility/measurements',json=poor).json()['comparable']
    assert client.get('/api/mobility/summary').json()['sides']['left']['count']==0
    assert client.put('/api/mobility/baseline/left',json={'record_id':'mobility-test-002'}).status_code==422


def test_baseline_matches_side_conditions_and_dates_and_survives_deletion(client):
    enabled(client)
    client.post('/api/mobility/measurements',json=body())
    # A same-day repeat must not appear as long-term progress.
    client.post('/api/mobility/measurements',json=body(request_id='mobility-test-002',observed_at='2026-01-01T09:00:00+08:00'))
    assert not client.get('/api/mobility/summary').json()['sides']['left']['comparison_available']
    newer=body(request_id='mobility-test-003',observed_at='2026-01-02T08:00:00+08:00')
    for trial in newer['trials']:
        trial['distance_cm']+=1
    client.post('/api/mobility/measurements',json=newer)
    trend=client.get('/api/mobility/summary').json()['sides']['left']
    assert trend['comparison_available'] and trend['change_cm']==1.0 and trend['count']==3
    assert client.put('/api/mobility/baseline/right',json={'record_id':'mobility-test-001'}).status_code==404
    assert client.put('/api/mobility/baseline/left',json={'record_id':'mobility-test-002'}).json()['sides']['left']['baseline_mode']=='selected'
    different=body(request_id='mobility-test-004',observed_at='2026-01-03T08:00:00+08:00',
        conditions={'surface':'same floor','ruler':'ruler-b','assessor':'self'})
    client.post('/api/mobility/measurements',json=different)
    trend=client.get('/api/mobility/summary').json()['sides']['left']
    assert trend['count']==1 and not trend['comparison_available'] and trend['selected_baseline_incompatible']
    assert client.delete('/api/mobility/measurements/mobility-test-004').status_code==200
    assert client.delete('/api/mobility/measurements/mobility-test-002').status_code==200
    assert client.get('/api/mobility/summary').json()['sides']['left']['baseline_mode']=='first_comparable'


def test_private_history_baseline_and_deletion_require_owner(client):
    enabled(client)
    client.post('/api/mobility/measurements',json=body())
    client.headers['X-Test-Owner']='owner-b'
    assert client.get('/api/mobility/settings').json()['storage_enabled'] is False
    assert client.get('/api/mobility/measurements').json()['items']==[]
    assert client.delete('/api/mobility/measurements/mobility-test-001').status_code==404
    enabled(client)
    assert client.put('/api/mobility/baseline/left',json={'record_id':'mobility-test-001'}).status_code==404
    assert client.delete('/api/mobility/measurements').status_code==200
    client.headers['X-Test-Owner']='owner-a'
    assert len(client.get('/api/mobility/measurements').json()['items'])==1
    assert client.delete('/api/mobility/measurements').status_code==200
    assert client.get('/api/mobility/summary').json()['sides']['left']['count']==0
    del client.headers['X-Test-Owner']
    assert client.get('/api/mobility/measurements').status_code==401


def test_anatomy_seed_graph_and_source_boundaries():
    from services.knowledge_seed import seed
    from knowledge_models import Bundle
    data=seed()
    Bundle.model_validate(data)
    items={v['id']:v for v in data['items']}
    assert data['version']!='foundation-20261022-v1'
    assert all(v in items for v in ('supraspinatus','infraspinatus','teres_minor','subscapularis','adductor_magnus','transversus_abdominis'))
    assert '并非独立的真性滑膜关节' in items['scapulothoracic']['facts']['joint_type']
    assert items['transversus_abdominis']['facts']['action_ids']==[]
    assert items['adductor_magnus']['facts']['landmark_ids']==['ischial_tuberosity','adductor_tubercle']
    assert len(items['guide_squat']['facts']['phase_notes'])==3
    assert not any(v.get('evidence_status')=='admin_reviewed' for v in items.values())
