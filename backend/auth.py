"""Account authentication, rotating sessions and server-side WeChat code exchange."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pwdlib import PasswordHash
from sqlalchemy import delete, insert, select, update
from starlette.responses import JSONResponse

try:
    from . import database as d
except ImportError:
    import database as d

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
POLICY_VERSION = '2026-10-18'
PUBLIC = {'/api/health', '/api/auth/config', '/api/auth/policies', '/api/auth/register', '/api/auth/register/verify',
          '/api/auth/login', '/api/auth/refresh', '/api/auth/password/forgot',
          '/api/auth/password/reset', '/api/auth/wechat/start', '/api/auth/wechat/exchange'}
_secrets = {}


def secret():
    configured = os.environ.get('AUTH_SECRET', '')
    if configured:
        if len(configured) < 32:
            raise RuntimeError('AUTH_SECRET must contain at least 32 characters')
        return configured
    if os.environ.get('APP_ENV') == 'production':
        raise RuntimeError('Production requires AUTH_SECRET')
    root = Path(os.environ.get('FIT_DATA_DIR', 'data'))
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'auth-secret'
    if str(path) not in _secrets:
        try:
            with path.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_urlsafe(48))
            path.chmod(0o600)
        except FileExistsError:
            pass
        _secrets[str(path)] = path.read_text(encoding='utf-8').strip()
    return _secrets[str(path)]


def digest(value):
    return hmac.new(secret().encode(), value.encode(), hashlib.sha256).hexdigest()


def encrypt(value):
    key = base64.urlsafe_b64encode(hashlib.sha256((secret() + ':mail').encode()).digest())
    return Fernet(key).encrypt(json.dumps(value).encode()).decode()


def decrypt(value):
    key = base64.urlsafe_b64encode(hashlib.sha256((secret() + ':mail').encode()).digest())
    return json.loads(Fernet(key).decrypt(value.encode()))


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)


class EmailInput(Input):
    email: str = Field(max_length=254)

    @field_validator('email')
    @classmethod
    def email_address(cls, value):
        value = value.strip().casefold()
        if value.count('@') != 1 or any(c.isspace() for c in value) or '.' not in value.split('@')[-1]:
            raise ValueError('请输入有效邮箱')
        return value


class Register(EmailInput):
    password: str = Field(min_length=15, max_length=128)
    policy_version: str = Field(max_length=40)
    invite_code: str = Field(default='', max_length=200)


class Verify(Input):
    challenge_id: str = Field(min_length=20, max_length=64)
    code: str = Field(pattern=r'^\d{6}$')
    device_name: str = Field(default='我的设备', min_length=1, max_length=100)


class Login(EmailInput):
    password: str = Field(min_length=1, max_length=128)
    device_name: str = Field(default='我的设备', min_length=1, max_length=100)


class Refresh(Input):
    refresh_token: str = Field(min_length=32, max_length=200)


class PasswordReset(Verify):
    password: str = Field(min_length=15, max_length=128)


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class EmailChange(EmailInput):
    password: str | None = Field(default=None, min_length=15, max_length=128)


class WechatStart(Input):
    code_challenge: str = Field(pattern=r'^[a-f0-9]{64}$')
    policy_version: str = Field(max_length=40)
    invite_code: str = Field(default='', max_length=200)
    purpose: str = Field(default='login', pattern=r'^(login|bind)$')


class WechatExchange(Input):
    state: str = Field(min_length=20, max_length=64)
    code: str = Field(min_length=1, max_length=512)
    code_verifier: str = Field(min_length=43, max_length=128)
    device_name: str = Field(default='我的设备', min_length=1, max_length=100)


def registration_allowed(invite):
    return os.environ.get('REGISTRATION_OPEN', '').lower() == 'true' or (
        bool(os.environ.get('AUTH_INVITE_CODE')) and
        hmac.compare_digest(invite, os.environ['AUTH_INVITE_CODE']))


def check_policy(version):
    if version != POLICY_VERSION:
        raise HTTPException(422, '请阅读并同意当前用户协议和隐私政策')


def mail_ready():
    return bool(os.environ.get('SMTP_HOST') and os.environ.get('SMTP_FROM'))


def wechat_ready():
    return bool(os.environ.get('WECHAT_APP_ID') and os.environ.get('WECHAT_APP_SECRET'))


def rate_limit(path, label, maximum=10, seconds=60):
    # Database-backed atomic counters work across processes. Never trust X-Forwarded-For here.
    bucket = int(time.time()) // seconds
    key = hashlib.sha256(f'{label}:{bucket}:{seconds}'.encode()).hexdigest()
    with d.get_engine(path).begin() as conn:
        stmt = d.dialect_insert(conn, d.rate_buckets).values(key=key, hits=1,
            expires_at=d.now() + timedelta(seconds=seconds * 2))
        stmt = stmt.on_conflict_do_update(index_elements=['key'],
            set_={'hits': d.rate_buckets.c.hits + 1}).returning(d.rate_buckets.c.hits)
        hits = conn.execute(stmt).scalar_one()
        conn.execute(delete(d.rate_buckets).where(d.rate_buckets.c.expires_at < d.now()))
    if hits > maximum:
        raise HTTPException(429, '操作过于频繁，请稍后重试', headers={'Retry-After': str(seconds)})


def throttle(path, request, subject='', maximum=10):
    ip = request.client.host if request.client else 'unknown'
    rate_limit(path, 'ip:' + ip, maximum * 3)
    if subject:
        rate_limit(path, 'subject:' + subject, maximum)


def account(row):
    return {k: row[k] for k in ('id', 'email', 'display_name', 'role')}


def new_user(conn, email=None, password_hash=None, name='训练者'):
    uid = str(uuid4())
    conn.execute(insert(d.users).values(id=uid, email=email, password_hash=password_hash,
        display_name=name, role='user', active=True, created_at=d.now()))
    conn.execute(insert(d.consents).values(id=str(uuid4()), user_id=uid,
        version=POLICY_VERSION, created_at=d.now()))
    return conn.execute(select(d.users).where(d.users.c.id == uid)).mappings().one()


def tokens(conn, session, user):
    refresh = secrets.token_urlsafe(48)
    conn.execute(insert(d.refresh_tokens).values(digest=digest(refresh), session_id=session['id'], used=False))
    access = jwt.encode({'sub': user['id'], 'sid': session['id'], 'iat': d.now(),
        'exp': d.now() + timedelta(minutes=15), 'iss': 'liftlab', 'aud': 'liftlab-app'}, secret(), algorithm='HS256')
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'bearer',
            'expires_in': 900, 'user': account(user)}


def create_session(conn, user, device):
    session = dict(id=str(uuid4()), user_id=user['id'], device_name=device,
        created_at=d.now(), last_used_at=d.now(), expires_at=d.now() + timedelta(days=30), revoked=False)
    conn.execute(insert(d.sessions).values(**session))
    return tokens(conn, session, user)


def authenticate(path, authorization):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, '请先登录', headers={'WWW-Authenticate': 'Bearer'})
    try:
        claims = jwt.decode(authorization[7:], secret(), algorithms=['HS256'],
            issuer='liftlab', audience='liftlab-app', options={'require': ['sub', 'sid', 'exp', 'iat']})
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, 'access_token_expired') from None
    except jwt.PyJWTError:
        raise HTTPException(401, '登录凭据无效') from None
    with d.get_engine(path).connect() as conn:
        user = conn.execute(select(d.users).where(d.users.c.id == claims['sub'], d.users.c.active.is_(True))).mappings().first()
        session = conn.execute(select(d.sessions).where(d.sessions.c.id == claims['sid'],
            d.sessions.c.user_id == claims['sub'], d.sessions.c.revoked.is_(False))).mappings().first()
    if not user or not session or d.aware(session['expires_at']) <= d.now() or d.aware(session['last_used_at']) < d.now() - timedelta(days=7):
        raise HTTPException(401, '登录已失效，请重新登录')
    return user, session


def install_middleware(app, path):
    @app.middleware('http')
    async def access_control(request, call_next):
        owner_token = session_token = lease = None
        try:
            url = request.url.path.rstrip('/')
            if url.startswith('/api') and url not in PUBLIC and request.method != 'OPTIONS':
                # SQL/password work is run off the event loop.
                from starlette.concurrency import run_in_threadpool
                user, session = await run_in_threadpool(authenticate, path, request.headers.get('Authorization'))
                owner_token = d.owner_context.set(user['id'])
                session_token = d.session_context.set(session['id'])
                request.state.user = user
                if url.startswith('/api/library') and request.method not in ('GET', 'HEAD') and user['role'] != 'admin':
                    raise HTTPException(403, '仅管理员可维护系统资料库')
                if request.method == 'POST' and (url in ('/api/plans/generate', '/api/movement/analyze', '/api/coach/messages') or url.endswith('/review')):
                    await run_in_threadpool(rate_limit, path, 'ai:' + user['id'], 6, 60)
                    await run_in_threadpool(rate_limit, path, 'ai-day:' + user['id'], 100, 86400)
                    def acquire():
                        lease_id = str(uuid4())
                        with d.get_engine(path).begin() as conn:
                            stmt = d.dialect_insert(conn, d.ai_leases).values(user_id=user['id'], lease_id=lease_id,
                                expires_at=d.now() + timedelta(minutes=4))
                            acquired = conn.execute(stmt.on_conflict_do_update(index_elements=['user_id'],
                                set_={'lease_id': lease_id, 'expires_at': d.now() + timedelta(minutes=4)},
                                where=d.ai_leases.c.expires_at < d.now()).returning(d.ai_leases.c.lease_id)).scalar_one_or_none()
                            if not acquired:
                                raise HTTPException(429, '上一条AI请求正在处理，请稍后重试')
                        return lease_id
                    lease = await run_in_threadpool(acquire)
            response = await call_next(request)
            if url.startswith('/api'):
                response.headers['Cache-Control'] = 'no-store'
            return response
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code,
                headers={**(exc.headers or {}), 'Cache-Control': 'no-store'})
        finally:
            if lease:
                with d.get_engine(path).begin() as conn:
                    conn.execute(delete(d.ai_leases).where(d.ai_leases.c.lease_id == lease))
            if session_token is not None:
                d.session_context.reset(session_token)
            if owner_token is not None:
                d.owner_context.reset(owner_token)


def challenge(conn, purpose, subject, payload):
    cid, code = secrets.token_urlsafe(32), f'{secrets.randbelow(1000000):06d}'
    conn.execute(insert(d.challenges).values(id=cid, purpose=purpose, subject=subject,
        digest=digest(cid + ':' + code), payload=payload, created_at=d.now(),
        expires_at=d.now() + timedelta(minutes=10), attempts=0, consumed=False))
    conn.execute(insert(d.outbox).values(id=str(uuid4()), recipient_digest=digest(subject), encrypted_message=encrypt(
        {'to': subject, 'subject': '练伴账号验证', 'body': f'你的验证码是 {code}，10 分钟内有效。如非本人操作，请忽略。'}),
        attempts=0, available_at=d.now(), sent=False))
    return cid


def consume(conn, cid, code, purpose):
    row = conn.execute(select(d.challenges).where(d.challenges.c.id == cid).with_for_update()).mappings().first()
    valid = row and row['purpose'] == purpose and not row['consumed'] and row['attempts'] < 5 and d.aware(row['expires_at']) > d.now()
    if not valid:
        return None
    conn.execute(update(d.challenges).where(d.challenges.c.id == cid).values(attempts=row['attempts'] + 1))
    if not hmac.compare_digest(row['digest'], digest(cid + ':' + code)):
        return None
    conn.execute(update(d.challenges).where(d.challenges.c.id == cid).values(consumed=True, payload={}))
    return row


async def wechat_identity(code):
    # AppSecret and provider tokens never leave the server. Do not log request URLs.
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get('https://api.weixin.qq.com/sns/oauth2/access_token', params={
                'appid': os.environ['WECHAT_APP_ID'], 'secret': os.environ['WECHAT_APP_SECRET'],
                'code': code, 'grant_type': 'authorization_code'})
            response.raise_for_status()
            data = response.json()
            if data.get('errcode') or not data.get('openid') or not data.get('access_token'):
                raise ValueError('provider rejected code')
            profile = await client.get('https://api.weixin.qq.com/sns/userinfo', params={
                'access_token': data['access_token'], 'openid': data['openid'], 'lang': 'zh_CN'})
            profile.raise_for_status()
            info = profile.json()
            if info.get('errcode') or info.get('openid') != data['openid']:
                raise ValueError('provider identity mismatch')
            return data['openid'], str(info.get('nickname') or '微信训练者')[:100]
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, '微信授权验证失败，请重新发起登录') from None


def router(path, data_dir):
    api = APIRouter(prefix='/api', tags=['accounts'])

    @api.get('/auth/policies')
    def policies():
        contact = os.environ.get('APP_SUPPORT_EMAIL', '运营者联系方式尚未配置（内测）')
        return {'version': POLICY_VERSION,
            'privacy': '练伴隐私政策（内测草案）\n\n账号信息、画像、饮食、聊天和训练记录用于提供私教服务。'
                '用户主动调用 AI 功能时，相关对话、画像和训练上下文会发送给已配置的模型服务商；'
                '视觉分析仅在用户主动上传或提交截图时发送相关素材。微信登录通过微信验证账号身份。'
                '我们不将私人记录作为公开资料库内容。你可以在账号与安全中导出记录或注销账号。'
                '注销立即撤销登录并清除在线个人记录与已记录媒体；备份按既定保留周期到期清除。'
                '相机、通知等权限在功能使用时按系统提示申请，你可以在系统设置撤回。'
                '正式发布前运营者需完善第三方清单、保存期限和权利请求方式。\n\n联系：' + contact,
            'terms': '练伴用户协议（内测草案）\n\n本服务提供训练记录、饮食估算与 AI 辅助建议。'
                '请如实填写个人情况，训练负荷与动作分析结果需结合实际确认；疼痛时停止相关动作。'
                '请妥善保管登录凭据，不冒用他人身份，不上传无权使用的媒体。'
                '账号仅用于本人数据管理，功能可用性与已配置服务有关。你可以随时退出或申请注销。'
                '正式开放前运营者需补充完整主体和服务条款。\n\n联系：' + contact}

    @api.get('/auth/config')
    def config():
        return {'email_enabled': mail_ready(), 'wechat_enabled': wechat_ready(),
            'wechat_app_id': os.environ.get('WECHAT_APP_ID', '') if wechat_ready() else '',
            'policy_version': POLICY_VERSION, 'registration_open': registration_allowed('')}

    @api.post('/auth/register', status_code=202)
    def register(body: Register, request: Request):
        check_policy(body.policy_version)
        throttle(path, request, body.email, 3)
        rate_limit(path, 'mail-day:' + body.email, 10, 86400)
        rate_limit(path, 'mail-minute:' + body.email, 1, 60)
        if not mail_ready():
            raise HTTPException(503, '验证邮件服务尚未配置')
        if not registration_allowed(body.invite_code):
            raise HTTPException(403, '当前为邀请注册，请填写有效邀请码')
        hashed = passwords.hash(body.password)
        with d.get_engine(path).begin() as conn:
            exists = conn.execute(select(d.users.c.id).where(d.users.c.email == body.email)).first()
            cid = challenge(conn, 'register', body.email, {'password_hash': hashed}) if not exists else secrets.token_urlsafe(32)
        return {'challenge_id': cid, 'message': '若该邮箱可用于注册，你将收到验证邮件'}

    @api.post('/auth/register/verify')
    def verify(body: Verify, request: Request):
        throttle(path, request, body.challenge_id)
        result = None
        with d.get_engine(path).begin() as conn:
            row = consume(conn, body.challenge_id, body.code, 'register')
            if row:
                # Unique email plus conflict-safe insert protects concurrent registration challenges.
                stmt = d.dialect_insert(conn, d.users).values(id=str(uuid4()), email=row['subject'],
                    password_hash=row['payload']['password_hash'], display_name='训练者', role='user', active=True, created_at=d.now())
                uid = conn.execute(stmt.on_conflict_do_nothing(index_elements=['email']).returning(d.users.c.id)).scalar_one_or_none()
                if uid:
                    conn.execute(insert(d.consents).values(id=str(uuid4()), user_id=uid, version=POLICY_VERSION, created_at=d.now()))
                    user = conn.execute(select(d.users).where(d.users.c.id == uid)).mappings().one()
                    result = create_session(conn, user, body.device_name)
        if not result:
            raise HTTPException(400, '验证码无效、已使用或账号无法注册')
        return result

    @api.post('/auth/login')
    def login(body: Login, request: Request):
        throttle(path, request, body.email, 5)
        with d.get_engine(path).begin() as conn:
            user = conn.execute(select(d.users).where(d.users.c.email == body.email).with_for_update()).mappings().first()
            valid = passwords.verify(body.password, user['password_hash'] if user and user['password_hash'] else DUMMY_HASH)
            if not valid or not user or not user['active']:
                raise HTTPException(401, '邮箱或密码错误')
            return create_session(conn, user, body.device_name)

    @api.post('/auth/refresh')
    def refresh(body: Refresh, request: Request):
        throttle(path, request, maximum=60)
        result = None
        with d.get_engine(path).begin() as conn:
            token = conn.execute(select(d.refresh_tokens).where(d.refresh_tokens.c.digest == digest(body.refresh_token))).mappings().first()
            if token:
                initial = conn.execute(select(d.sessions).where(d.sessions.c.id == token['session_id'])).mappings().first()
                if initial:
                    user = conn.execute(select(d.users).where(d.users.c.id == initial['user_id']).with_for_update()).mappings().first()
                    session = conn.execute(select(d.sessions).where(d.sessions.c.id == token['session_id']).with_for_update()).mappings().first()
                    token = conn.execute(select(d.refresh_tokens).where(d.refresh_tokens.c.digest == token['digest']).with_for_update()).mappings().first()
                    valid = user and user['active'] and not session['revoked'] and d.aware(session['expires_at']) > d.now() and d.aware(session['last_used_at']) > d.now() - timedelta(days=7)
                    if token['used']:
                        conn.execute(update(d.sessions).where(d.sessions.c.id == session['id']).values(revoked=True))
                    elif valid:
                        conn.execute(update(d.refresh_tokens).where(d.refresh_tokens.c.digest == token['digest']).values(used=True))
                        conn.execute(update(d.sessions).where(d.sessions.c.id == session['id']).values(last_used_at=d.now()))
                        result = tokens(conn, session, user)
        if not result:
            raise HTTPException(401, '登录已失效，请重新登录')
        return result

    @api.post('/auth/password/forgot', status_code=202)
    def forgot(body: EmailInput, request: Request):
        throttle(path, request, body.email, 3)
        rate_limit(path, 'mail-minute:' + body.email, 1, 60)
        rate_limit(path, 'mail-day:' + body.email, 10, 86400)
        if not mail_ready():
            raise HTTPException(503, '验证邮件服务尚未配置')
        with d.get_engine(path).begin() as conn:
            user = conn.execute(select(d.users).where(d.users.c.email == body.email, d.users.c.active.is_(True))).mappings().first()
            cid = challenge(conn, 'reset', body.email, {'user_id': user['id']}) if user else secrets.token_urlsafe(32)
        return {'challenge_id': cid, 'message': '若账号可用，你将收到重置邮件'}

    @api.post('/auth/password/reset')
    def reset(body: PasswordReset, request: Request):
        throttle(path, request, body.challenge_id)
        hashed = passwords.hash(body.password)
        valid = False
        with d.get_engine(path).begin() as conn:
            row = consume(conn, body.challenge_id, body.code, 'reset')
            if row:
                user = conn.execute(select(d.users).where(d.users.c.id == row['payload']['user_id'], d.users.c.active.is_(True)).with_for_update()).mappings().first()
                if user:
                    conn.execute(update(d.users).where(d.users.c.id == user['id']).values(password_hash=hashed))
                    conn.execute(update(d.sessions).where(d.sessions.c.user_id == user['id']).values(revoked=True))
                    valid = True
        if not valid:
            raise HTTPException(400, '验证码无效或已过期')
        return {'message': '密码已重置，请重新登录'}

    @api.post('/auth/password/change')
    def change(body: PasswordChange):
        with d.get_engine(path).begin() as conn:
            user = conn.execute(select(d.users).where(d.users.c.id == d.owner()).with_for_update()).mappings().one()
            if not user['password_hash'] or not passwords.verify(body.current_password, user['password_hash']):
                raise HTTPException(400, '当前密码不正确；微信账号请先绑定邮箱')
            conn.execute(update(d.users).where(d.users.c.id == d.owner()).values(password_hash=passwords.hash(body.new_password)))
            conn.execute(update(d.sessions).where(d.sessions.c.user_id == d.owner()).values(revoked=True))
        return {'message': '密码已修改，请重新登录'}

    @api.get('/me')
    def me(request: Request):
        return account(request.state.user)

    @api.post('/me/email/start', status_code=202)
    def email_start(body: EmailChange, request: Request):
        throttle(path, request, body.email, 3)
        rate_limit(path, 'mail-minute:' + body.email, 1, 60)
        rate_limit(path, 'mail-day:' + body.email, 10, 86400)
        if not mail_ready():
            raise HTTPException(503, '验证邮件服务尚未配置')
        with d.get_engine(path).begin() as conn:
            session = conn.execute(select(d.sessions).where(d.sessions.c.id == d.session_context.get())).mappings().one()
            if d.aware(session['created_at']) < d.now() - timedelta(minutes=5):
                raise HTTPException(403, '请重新登录后在5分钟内绑定邮箱')
            current = request.state.user
            if not current['password_hash'] and not body.password:
                raise HTTPException(422, '请设置至少15个字符的邮箱登录密码')
            exists = conn.execute(select(d.users.c.id).where(d.users.c.email == body.email, d.users.c.id != d.owner())).first()
            cid = secrets.token_urlsafe(32)
            if not exists:
                cid = challenge(conn, 'email', body.email, {'user_id': d.owner(), 'session_id': d.session_context.get(),
                    'password_hash': passwords.hash(body.password) if body.password else None})
        return {'challenge_id': cid, 'message': '若该邮箱可绑定，你将收到验证邮件'}

    @api.post('/me/email/verify')
    def email_verify(body: Verify):
        rate_limit(path, 'email-verify:' + d.owner(), 10, 60)
        result = None
        with d.get_engine(path).begin() as conn:
            user = conn.execute(select(d.users).where(d.users.c.id == d.owner(), d.users.c.active.is_(True)).with_for_update()).mappings().first()
            row = consume(conn, body.challenge_id, body.code, 'email')
            if user and row and row['payload']['user_id'] == d.owner() and row['payload']['session_id'] == d.session_context.get():
                exists = conn.execute(select(d.users.c.id).where(d.users.c.email == row['subject'], d.users.c.id != d.owner())).first()
                if not exists:
                    conn.execute(update(d.users).where(d.users.c.id == d.owner()).values(email=row['subject'],
                        password_hash=row['payload']['password_hash'] or user['password_hash']))
                    if user['email'] and user['email'] != row['subject']:
                        conn.execute(insert(d.outbox).values(id=str(uuid4()), recipient_digest=digest(user['email']),
                            encrypted_message=encrypt({'to': user['email'], 'subject': '练伴邮箱变更通知',
                                'body': '你的练伴账号绑定邮箱已变更。如非本人操作，请联系运营者。'}),
                            attempts=0, available_at=d.now(), sent=False))
                    result = {'ok': True}
        if not result:
            raise HTTPException(400, '验证码无效或邮箱无法绑定')
        return result

    @api.get('/auth/sessions')
    def devices():
        with d.get_engine(path).connect() as conn:
            rows = conn.execute(select(d.sessions).where(d.sessions.c.user_id == d.owner(), d.sessions.c.revoked.is_(False))).mappings()
            return [{'id': r['id'], 'device_name': r['device_name'], 'last_used_at': r['last_used_at'],
                'expires_at': r['expires_at'], 'current': r['id'] == d.session_context.get()} for r in rows]

    @api.delete('/auth/sessions/{sid}')
    def revoke(sid: str):
        with d.get_engine(path).begin() as conn:
            conn.execute(select(d.users).where(d.users.c.id == d.owner()).with_for_update()).one()
            result = conn.execute(update(d.sessions).where(d.sessions.c.id == sid, d.sessions.c.user_id == d.owner()).values(revoked=True))
            if not result.rowcount:
                raise HTTPException(404, '会话不存在')
        return {'ok': True}

    @api.post('/auth/logout')
    def logout():
        return revoke(d.session_context.get())

    @api.post('/auth/logout-all')
    def logout_all():
        with d.get_engine(path).begin() as conn:
            conn.execute(select(d.users).where(d.users.c.id == d.owner()).with_for_update()).one()
            conn.execute(update(d.sessions).where(d.sessions.c.user_id == d.owner()).values(revoked=True))
        return {'ok': True}

    @api.get('/me/export')
    def export():
        with d.connection(path) as store:
            rows = store.conn.execute(select(d.records_table.c.kind, d.records_table.c.id,
                d.records_table.c.payload).where(d.records_table.c.user_id == d.owner())).mappings()
            return {'exported_at': d.now(), 'records': list(rows),
                'media_note': '媒体元数据包含于记录中，文件通过本人授权的媒体下载接口获取'}

    @api.delete('/me')
    def remove_account(request: Request):
        # Only a freshly authenticated session may delete an account.
        with d.get_engine(path).begin() as conn:
            conn.execute(select(d.users).where(d.users.c.id == d.owner()).with_for_update()).one()
            session = conn.execute(select(d.sessions).where(d.sessions.c.id == d.session_context.get())).mappings().one()
            if d.aware(session['created_at']) < d.now() - timedelta(minutes=5):
                raise HTTPException(403, '请重新登录后在5分钟内注销')
            files = conn.execute(select(d.records_table.c.payload).where(d.records_table.c.user_id == d.owner(), d.records_table.c.kind == 'media')).scalars().all()
            email = request.state.user['email']
            if email:
                conn.execute(delete(d.challenges).where(d.challenges.c.subject == email))
                conn.execute(delete(d.outbox).where(d.outbox.c.recipient_digest == digest(email)))
            # Keep a disabled tombstone so in-flight model calls cannot recreate user data.
            conn.execute(update(d.users).where(d.users.c.id == d.owner()).values(active=False,
                email=None, password_hash=None, display_name='已注销用户'))
            for table in (d.records_table, d.identities, d.sessions, d.consents):
                conn.execute(delete(table).where(table.c.user_id == d.owner()))
        root = (data_dir / 'uploads').resolve()
        for item in files:
            target = (root / item.get('stored_name', '')).resolve()
            if target.parent == root and target.is_file():
                target.unlink(missing_ok=True)
        return {'ok': True, 'message': '账号已注销；历史备份按保留周期清除'}

    @api.post('/auth/wechat/start')
    def wechat_start(body: WechatStart, request: Request):
        check_policy(body.policy_version)
        throttle(path, request)
        if not wechat_ready():
            raise HTTPException(503, '微信登录尚未配置，请使用邮箱登录')
        uid = sid = None
        if body.purpose == 'bind':
            user, session = authenticate(path, request.headers.get('Authorization'))
            if d.aware(session['created_at']) < d.now() - timedelta(minutes=5):
                raise HTTPException(403, '请重新登录后绑定微信')
            uid, sid = user['id'], session['id']
        state = secrets.token_urlsafe(32)
        with d.get_engine(path).begin() as conn:
            conn.execute(insert(d.challenges).values(id=state, purpose='wechat', subject='wechat',
                digest=body.code_challenge, payload={'user_id': uid, 'session_id': sid,
                    'can_register': registration_allowed(body.invite_code)}, created_at=d.now(),
                expires_at=d.now() + timedelta(minutes=5), attempts=0, consumed=False))
        return {'state': state, 'app_id': os.environ['WECHAT_APP_ID'], 'scope': 'snsapi_userinfo'}

    @api.post('/auth/wechat/exchange')
    async def wechat_exchange(body: WechatExchange, request: Request):
        throttle(path, request)
        if not wechat_ready():
            raise HTTPException(503, '微信登录尚未配置')
        state = None
        with d.get_engine(path).begin() as conn:
            row = conn.execute(select(d.challenges).where(d.challenges.c.id == body.state).with_for_update()).mappings().first()
            if row and row['purpose'] == 'wechat' and not row['consumed'] and d.aware(row['expires_at']) > d.now():
                if hmac.compare_digest(row['digest'], hashlib.sha256(body.code_verifier.encode()).hexdigest()):
                    state = dict(row['payload'])
                    conn.execute(update(d.challenges).where(d.challenges.c.id == body.state).values(consumed=True, payload={}))
        if state is None:
            raise HTTPException(400, '微信授权状态无效，请重新登录')
        openid, name = await wechat_identity(body.code)
        provider = 'wechat:' + os.environ['WECHAT_APP_ID']
        # Same provider subject is serialized before lookup/create, across all workers.
        with d.get_engine(path).begin() as conn:
            if conn.dialect.name == 'postgresql':
                from sqlalchemy import text
                lock_id = int.from_bytes(hashlib.sha256((provider + openid).encode()).digest()[:8], 'big', signed=True)
                conn.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})
            identity = conn.execute(select(d.identities).where(d.identities.c.provider == provider, d.identities.c.subject == openid)).mappings().first()
            if state['user_id']:
                user, session = authenticate(path, request.headers.get('Authorization'))
                if user['id'] != state['user_id'] or session['id'] != state['session_id']:
                    raise HTTPException(403, '绑定账号状态已变化，请重试')
                if identity and identity['user_id'] != user['id']:
                    raise HTTPException(409, '该微信已绑定其他账号，不会自动合并')
                locked = conn.execute(select(d.users).where(d.users.c.id == user['id'], d.users.c.active.is_(True)).with_for_update()).first()
                if not locked:
                    raise HTTPException(401, '账号已停用')
                if not identity:
                    conn.execute(insert(d.identities).values(provider=provider, subject=openid, user_id=user['id']))
                return {'bound': True}
            if identity:
                user = conn.execute(select(d.users).where(d.users.c.id == identity['user_id']).with_for_update()).mappings().one()
                if not user['active']:
                    raise HTTPException(403, '账号已停用')
            else:
                if not state['can_register']:
                    raise HTTPException(403, '当前为邀请注册，请填写有效邀请码')
                user = new_user(conn, name=name)
                conn.execute(insert(d.identities).values(provider=provider, subject=openid, user_id=user['id']))
            return create_session(conn, user, body.device_name)

    return api
