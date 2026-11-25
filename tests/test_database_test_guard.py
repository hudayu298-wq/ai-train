import pytest
from backend.test_support import assert_isolated_database


@pytest.mark.parametrize('settings',[
    {},
    {'APP_ENV':'production','DATABASE_URL':''},
    {'APP_ENV':'test','DATABASE_URL':'postgresql://app:synthetic@db.example.test/main'},
    {'APP_ENV':'test','DATABASE_URL':'postgresql://audit_app_fixture:synthetic@127.0.0.1:5432/lianban_audit_fixture','DISPOSABLE_POSTGRES_NONCE':'x'*32},
])
def test_destructive_fixture_rejects_unsafe_environment_before_connecting(monkeypatch,settings):
    import psycopg
    def forbidden(*args,**kwargs):raise AssertionError('unsafe environment attempted connection')
    monkeypatch.setattr(psycopg,'connect',forbidden)
    for key in ('APP_ENV','DATABASE_URL','DISPOSABLE_POSTGRES_NONCE'):monkeypatch.delenv(key,raising=False)
    for key,value in settings.items():monkeypatch.setenv(key,value)
    with pytest.raises(RuntimeError):assert_isolated_database()
