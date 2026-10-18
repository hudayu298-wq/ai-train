"""Auth integration tests, also run unchanged against a disposable PostgreSQL DB."""
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select, update

# If the business suite was loaded first, share its isolated application.
if 'app' not in sys.modules:
    _temp = tempfile.TemporaryDirectory()
    os.environ['FIT_DATA_DIR'] = _temp.name
    sys.path.insert(0, str(Path(__file__).parent))
app = importlib.import_module('app')
d, auth = app.database, app.auth
client = TestClient(app.app)
PASSWORD = 'correct horse battery staple 2026'


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    monkeypatch.setenv('REGISTRATION_OPEN', 'true')
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_FROM', 'noreply@example.test')
    monkeypatch.setenv('WECHAT_APP_ID', 'wx-test-app')
    monkeypatch.setenv('WECHAT_APP_SECRET', 'mock-server-secret')
    with d.get_engine(app.DB).begin() as conn:
        conn.execute(delete(d.users))
        conn.execute(delete(d.challenges))
        conn.execute(delete(d.outbox))
        conn.execute(delete(d.rate_buckets))
    client.headers.pop('Authorization', None)


def user(email='a@example.test', role='user'):
    with d.get_engine(app.DB).begin() as conn:
        row = auth.new_user(conn, email, auth.passwords.hash(PASSWORD))
        conn.execute(update(d.users).where(d.users.c.id == row['id']).values(role=role))
        return auth.create_session(conn, row, 'integration test')


def headers(tokens):
    return {'Authorization': 'Bearer ' + tokens['access_token']}


def mail_code():
    with d.get_engine(app.DB).connect() as conn:
        message = conn.execute(select(d.outbox.c.encrypted_message)).scalar_one()
    return re.search(r'\d{6}', auth.decrypt(message)['body']).group()


def test_register_verification_is_single_use_and_does_not_leak_password():
    body = {'email': 'new@example.test', 'password': PASSWORD, 'policy_version': auth.POLICY_VERSION}
    started = client.post('/api/auth/register', json=body)
    assert started.status_code == 202
    assert PASSWORD not in started.text
    verify = {'challenge_id': started.json()['challenge_id'], 'code': mail_code()}
    result = client.post('/api/auth/register/verify', json=verify)
    assert result.status_code == 200
    assert result.json()['user']['email'] == body['email']
    assert client.post('/api/auth/register/verify', json=verify).status_code == 400
    invalid = client.post('/api/auth/register', json={**body, 'password': 'do-not-echo-me'})
    assert invalid.status_code == 422 and 'do-not-echo-me' not in invalid.text


def test_wrong_verification_attempts_are_committed():
    started = client.post('/api/auth/register', json={'email': 'new@example.test', 'password': PASSWORD, 'policy_version': auth.POLICY_VERSION}).json()
    correct = mail_code()
    wrong = '111111' if correct != '111111' else '222222'
    for _ in range(5):
        assert client.post('/api/auth/register/verify', json={'challenge_id': started['challenge_id'], 'code': wrong}).status_code == 400
    assert client.post('/api/auth/register/verify', json={'challenge_id': started['challenge_id'], 'code': correct}).status_code == 400


def test_private_routes_and_library_admin_permissions():
    assert client.get('/api/profile').status_code == 401
    assert client.get('/api/library/foods').status_code == 401
    assert client.get('/api/health').status_code == 200
    tokens = user()
    assert client.get('/api/library/foods', headers=headers(tokens)).status_code == 200
    assert client.delete('/api/library/foods/rice', headers=headers(tokens)).status_code == 403


def test_refresh_rotation_reuse_revokes_entire_session():
    old = user()
    new = client.post('/api/auth/refresh', json={'refresh_token': old['refresh_token']})
    assert new.status_code == 200 and new.json()['refresh_token'] != old['refresh_token']
    assert client.post('/api/auth/refresh', json={'refresh_token': old['refresh_token']}).status_code == 401
    assert client.get('/api/me', headers=headers(new.json())).status_code == 401
    assert client.post('/api/auth/refresh', json={'refresh_token': new.json()['refresh_token']}).status_code == 401


def test_users_are_isolated_in_all_document_types_and_media(tmp_path):
    a, b = user(), user('b@example.test')
    for tokens in (a, b):
        context = d.owner_context.set(tokens['user']['id'])
        try:
            with app.connection() as db:
                for kind in ('profile', 'coach_profile', 'coach_turn', 'coach_reminders', 'rm', 'plan', 'meal', 'workout', 'movement_analysis'):
                    db.write(kind, 'same-id', {'owner_marker': tokens['user']['id']})
                assert all(row['owner_marker'] == tokens['user']['id'] for row in db.records('profile'))
                assert db.read('profile', 'same-id')['owner_marker'] == tokens['user']['id']
        finally:
            d.owner_context.reset(context)
    assert client.get('/api/profile', headers=headers(a)).json()['owner_marker'] == a['user']['id']
    assert client.get('/api/profile', headers=headers(b)).json()['owner_marker'] == b['user']['id']
    uploaded = client.post('/api/media', headers=headers(a), data={'kind': 'meal'}, files={'file': ('meal.png', b'private-test', 'image/png')})
    assert uploaded.status_code == 200
    media_id = uploaded.json()['id']
    assert client.get(f'/api/media/{media_id}/file', headers=headers(a)).content == b'private-test'
    assert client.get(f'/api/media/{media_id}/file', headers=headers(b)).status_code == 404
    assert client.get('/api/media', headers=headers(b)).json() == []
    assert client.post('/api/workouts/workout-a/review', headers=headers(b), json={}).status_code == 404


def test_logout_and_password_reset_revoke_sessions():
    tokens = user()
    assert client.post('/api/auth/logout', headers=headers(tokens)).status_code == 200
    assert client.get('/api/me', headers=headers(tokens)).status_code == 401
    logged = client.post('/api/auth/login', json={'email': 'a@example.test', 'password': PASSWORD}).json()
    started = client.post('/api/auth/password/forgot', json={'email': 'a@example.test'}).json()
    assert client.post('/api/auth/password/reset', json={'challenge_id': started['challenge_id'], 'code': mail_code(), 'password': PASSWORD + 'new'}).status_code == 200
    assert client.get('/api/me', headers=headers(logged)).status_code == 401
    assert client.post('/api/auth/login', json={'email': 'a@example.test', 'password': PASSWORD}).status_code == 401


def test_wechat_state_verifier_replay_identity_and_binding_conflict(monkeypatch):
    async def fake_identity(code):
        assert code == 'provider-authorization-code'
        return 'provider-openid', '微信测试用户'
    monkeypatch.setattr(auth, 'wechat_identity', fake_identity)
    verifier = 'v' * 64
    payload = {'code_challenge': hashlib.sha256(verifier.encode()).hexdigest(), 'policy_version': auth.POLICY_VERSION}
    start = client.post('/api/auth/wechat/start', json=payload).json()
    exchange = {'state': start['state'], 'code': 'provider-authorization-code', 'code_verifier': verifier}
    assert client.post('/api/auth/wechat/exchange', json={**exchange, 'code_verifier': 'x' * 64}).status_code == 400
    result = client.post('/api/auth/wechat/exchange', json=exchange)
    assert result.status_code == 200
    assert result.json()['user']['email'] is None
    assert 'mock-server-secret' not in result.text
    assert client.post('/api/auth/wechat/exchange', json=exchange).status_code == 400
    start2 = client.post('/api/auth/wechat/start', json=payload).json()
    again = client.post('/api/auth/wechat/exchange', json={**exchange, 'state': start2['state']})
    assert again.json()['user']['id'] == result.json()['user']['id']
    other = user('other@example.test')
    binding = client.post('/api/auth/wechat/start', headers=headers(other), json={**payload, 'purpose': 'bind'}).json()
    assert client.post('/api/auth/wechat/exchange', headers=headers(other), json={**exchange, 'state': binding['state']}).status_code == 409


def test_delete_account_cannot_be_recreated_by_inflight_ai():
    tokens = user()
    assert client.delete('/api/me', headers=headers(tokens)).status_code == 200
    assert client.get('/api/me', headers=headers(tokens)).status_code == 401
    context = d.owner_context.set(tokens['user']['id'])
    try:
        with pytest.raises(Exception, match='401'):
            with app.connection() as db:
                db.write('coach_turn', 'in-flight', {'reply': 'late'})
    finally:
        d.owner_context.reset(context)
    with d.get_engine(app.DB).connect() as conn:
        assert not conn.execute(select(d.records_table)).first()


def test_wechat_account_can_bind_verified_email_and_login_with_password():
    with d.get_engine(app.DB).begin() as conn:
        row = auth.new_user(conn, name='微信用户')
        tokens = auth.create_session(conn, row, 'phone')
    started = client.post('/api/me/email/start', headers=headers(tokens),
        json={'email': 'bound@example.test', 'password': PASSWORD})
    assert started.status_code == 202
    assert client.post('/api/me/email/verify', headers=headers(tokens),
        json={'challenge_id': started.json()['challenge_id'], 'code': mail_code()}).status_code == 200
    assert client.post('/api/auth/login', json={'email': 'bound@example.test', 'password': PASSWORD}).json()['user']['id'] == row['id']


@pytest.mark.parametrize('ssl_enabled', [True, False])
def test_mail_worker_delivers_encrypted_queue_with_tls(monkeypatch, ssl_enabled):
    from scripts import send_mail
    # The script can also be imported as backend.*, while the legacy suite imports app directly.
    original_engine = d.get_engine
    monkeypatch.setattr(send_mail.d, 'get_engine', lambda: original_engine(app.DB))
    monkeypatch.setattr(send_mail, 'auth', auth)
    monkeypatch.setenv('SMTP_SSL', str(ssl_enabled).lower())
    monkeypatch.setenv('SMTP_USERNAME', 'smtp-test-user')
    monkeypatch.setenv('SMTP_PASSWORD', 'smtp-test-authorization')
    sent, tls = [], []
    class FakeSmtp:
        def __init__(self, *args, **kwargs):
            assert kwargs.get('context') is not None if ssl_enabled else True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, *, context): tls.append(True)
        def login(self, username, password):
            assert (username, password) == ('smtp-test-user', 'smtp-test-authorization')
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr(send_mail.smtplib, 'SMTP_SSL' if ssl_enabled else 'SMTP', FakeSmtp)
    with original_engine(app.DB).begin() as conn:
        auth.challenge(conn, 'register', 'mail@example.test', {'password_hash': auth.DUMMY_HASH})
    send_mail.drain()
    assert len(sent) == 1 and sent[0]['To'] == 'mail@example.test'
    assert bool(tls) is not ssl_enabled
    with original_engine(app.DB).connect() as conn:
        row = conn.execute(select(d.outbox)).mappings().one()
        assert row['sent'] and row['encrypted_message'] == ''


@pytest.mark.skipif(not os.environ.get('DATABASE_URL', '').startswith('postgresql'), reason='Requires disposable PostgreSQL')
def test_postgres_concurrent_wechat_login_creates_one_account(monkeypatch):
    async def fake_identity(code):
        return 'same-provider-openid', '微信用户'
    monkeypatch.setattr(auth, 'wechat_identity', fake_identity)
    verifier = 'v' * 64
    challenges = [client.post('/api/auth/wechat/start', json={
        'code_challenge': hashlib.sha256(verifier.encode()).hexdigest(), 'policy_version': auth.POLICY_VERSION}).json()['state'] for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda state: client.post('/api/auth/wechat/exchange', json={
            'state': state, 'code_verifier': verifier, 'code': 'different-provider-codes'}), challenges))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json()['user']['id'] == results[1].json()['user']['id']


@pytest.mark.skipif(not os.environ.get('DATABASE_URL', '').startswith('postgresql'), reason='Requires disposable PostgreSQL')
def test_postgres_concurrent_refresh_only_one_succeeds():
    tokens = user()
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: client.post('/api/auth/refresh', json={'refresh_token': tokens['refresh_token']}).status_code, range(2)))
    assert sorted(statuses) == [200, 401]
