"""Fail before importing the app if destructive fixtures are not isolated."""
import os


def assert_isolated_database():
    if os.environ.get('APP_ENV')!='test' or 'DATABASE_URL' not in os.environ:
        raise RuntimeError('Refusing destructive fixtures: explicitly set APP_ENV=test and DATABASE_URL (empty for temporary SQLite).')
    url=os.environ['DATABASE_URL']
    if not url:return
    from sqlalchemy.engine import make_url
    parsed=make_url(url)
    nonce=os.environ.get('DISPOSABLE_POSTGRES_NONCE','')
    if (not parsed.drivername.startswith('postgresql') or parsed.host not in ('127.0.0.1','localhost')
        or not parsed.database or not parsed.database.startswith('lianban_audit_')
        or not parsed.username or not parsed.username.startswith('audit_app_')
        or not parsed.port or parsed.port==5432 or len(nonce)<24):
        raise RuntimeError('Refusing destructive fixtures: use the project disposable PostgreSQL runner.')
    import psycopg
    with psycopg.connect(url.replace('postgresql+psycopg://','postgresql://',1),connect_timeout=3) as conn:
        value=conn.execute("SELECT current_setting('lianban.audit_nonce',true)").fetchone()[0]
        if value!=nonce:raise RuntimeError('Disposable PostgreSQL marker mismatch; tests were not started.')
