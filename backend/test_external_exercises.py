"""Full upstream coverage, license separation, linked filters and stable identities."""
import json
from pathlib import Path
from PIL import Image,ImageStat
from test_app import module,client,isolate_records,PLAN
from external_exercises import bundle
from exercise_taxonomy import GROUPS,classify


def test_full_sources_are_accounted_for_and_every_entry_has_joint_categories():
    data=bundle();mapping=data['source_record_map']
    assert sum(k.startswith('dataset:') for k in mapping)==1324
    assert sum(k.startswith('guide:') for k in mapping)==302
    rows={r['id']:r for r in data['items']};rows.update(data['legacy_bindings'])
    assert set(mapping.values())<=rows.keys()
    for source,key in mapping.items():
        provider,source_id=source.split(':',1)
        expected='workout-guide' if provider=='guide' else 'exercises-dataset'
        assert any(r['provider']==expected and r['id']==source_id for r in rows[key]['upstream_refs'])
    for row in rows.values():
        assert row['joint_action_ids'] and set(row['joint_action_ids'])<=GROUPS.keys()
        assert row['joint_action_categories']==[GROUPS[k][0] for k in row['joint_action_ids']]
        assert row['classification']['status'] in ('rule_inferred','needs_review')
        assert row['realtime_supported'] is False
        assert row['technique']['common_errors']==[]
        assert all('gymvisual' not in str(row.get('demo',{})).lower() for _ in [0])


def test_every_demo_is_visible_animated_and_has_traceable_licenses():
    folder=module.ROOT/'backend/assets/exercise-demos/external'
    manifest=json.loads((folder/'PROVENANCE.json').read_text(encoding='utf8'))
    assert len(manifest['assets'])==302
    assert len(list(folder.glob('*.gif')))==302
    for record in manifest['assets']:
        with Image.open(folder/(record['slug']+'.gif')) as im:
            assert im.size==(512,512) and im.n_frames>=3
            assert max(ImageStat.Stat(im.convert('RGB')).stddev)>5
        assert len(record['source_png_sha256'])==3
    assert 'CC BY-SA 4.0' in (folder/'LICENSE-ASSETS.txt').read_text(encoding='utf8')
    assert 'MEDIA EXCEPTION' in (folder/'DATA-LICENSE.txt').read_text(encoding='utf8')


def test_full_catalog_paginates_and_joint_body_facets_link_without_identity_changes():
    response=client.get('/api/library/exercises',params={'limit':200,'offset':80}).json()
    assert response['total']==97 and len(response['items'])==17
    elbow=client.get('/api/library/exercises',params={'category':'肘关节：伸展','body_part':'胸部','limit':200}).json()
    assert elbow['total']>5 and 'bench' in {r['id'] for r in elbow['items']}
    assert all('肘关节：伸展' in r['joint_action_categories'] and '胸部' in r['body_regions'] for r in elbow['items'])
    assert client.get('/api/library/exercises?type=cardio').json()['total']>0
    assert all(r['type']=='bodyweight' for r in bundle()['items'] if r['equipment'] in ('Pull-up Bar','Wall','Chair'))
    current=client.get('/api/library/exercises/bench').json()
    assert current['name']=='平板杠铃卧推' and current['realtime_supported']
    assert current['demo']['url'].endswith('external/bench-press.gif')
    # Re-initialization never revives an archived external exercise.
    key=bundle()['source_record_map']['dataset:0026']
    assert client.delete('/api/library/exercises/'+key).status_code==200
    module.library.initialize(module.connection)
    assert client.get('/api/library/exercises/'+key).status_code==404


def test_external_weighted_exercise_can_be_selected_and_context_is_unreviewed():
    row=next(r for r in bundle()['items'] if r['type']=='weighted')
    plan=json.loads(json.dumps(PLAN));plan['days'][0]['exercises'][0]['exercise_id']=row['id']
    assert client.post('/api/plans',json=plan).status_code==200
    context=client.get('/api/library/exercises/'+row['id']+'/analysis-context').json()
    assert context['reference']['classification']['status'] in ('rule_inferred','needs_review')
    assert context['allowed_cue_ids']==[] and not context['demo_is_measurement_reference']
    assert 'technique' not in next(e for e in client.get('/api/catalog?extended=true').json()['exercises'] if e['id']==row['id'])


def test_name_rules_do_not_confuse_machine_prefix_or_grip_with_core_or_finger_action():
    assert 'trunk_stability' not in classify('lever seated calf raise','calves')['joint_action_ids']
    assert 'finger' not in classify('barbell close grip curl','biceps')['joint_action_ids']
    assert {'hip_extension','knee_extension'}<=set(classify('barbell full squat','glutes')['joint_action_ids'])
    assert 'elbow_extension' in classify('cable rope triceps pushdown','triceps')['joint_action_ids']
    assert 'neck' not in classify('cable behind neck pulldown','lats')['joint_action_ids']
    assert 'trunk_rotation' not in classify('dumbbell palm rotational row','lats')['joint_action_ids']
