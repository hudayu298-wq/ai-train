"""Disposable portable PostgreSQL acceptance. Never accepts an existing DB URL.

Creates a private cluster under .tools, binds loopback to a free port, migrates
as a separate owner and runs tests as an unprivileged app role. Passwords stay
in memory/child environments; logs redact secrets. The cluster always stops.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tarfile
from datetime import datetime,timezone
from uuid import uuid4

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.setup_postgres_audit import VERSION,setup
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb


def run(test_scope='all'):
    binary=ROOT/'.tools/postgres-audit'/VERSION/'pgsql/bin'
    if not (binary/'postgres.exe').is_file():binary=setup()
    identifier=uuid4().hex
    folder=(ROOT/'.tools/postgres-acceptance'/identifier).resolve()
    if not folder.is_relative_to((ROOT/'.tools/postgres-acceptance').resolve()):raise RuntimeError('Unexpected workspace')
    folder.mkdir(parents=True)
    identity=os.environ.get('USERDOMAIN','')+'\\'+getpass.getuser()
    subprocess.run(['icacls',str(folder),'/inheritance:r','/grant:r',identity+':(OI)(CI)F'],check=True,capture_output=True)
    data=folder/'cluster'
    passwords={key:secrets.token_urlsafe(36) for key in ('bootstrap','owner','app')}
    owner='audit_owner_'+identifier[:8];app='audit_app_'+identifier[:8]
    database='lianban_audit_'+identifier
    nonce=secrets.token_hex(24)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    environment={**os.environ,'APP_ENV':'test','DATABASE_URL':'','FIT_DATA_DIR':str(folder/'app-data'),
        'KNOWLEDGE_RETRIEVAL_MODE':'bm25','AGENT_ROUTING_MODE':'rules','AGENT_DECISION_PROVIDER':'local',
        'AUTH_SECRET':secrets.token_urlsafe(48),'DISPOSABLE_POSTGRES_NONCE':nonce,'PYTHONUTF8':'1',
        'REDIS_URL':'redis://127.0.0.1:6379/15','REDIS_CACHE_NAMESPACE':'pg-audit-'+identifier}
    redactions=[*passwords.values(),environment['AUTH_SECRET']]
    report={'run_id':identifier,'version':VERSION,'port':port,'listen':'127.0.0.1',
        'scope':'synthetic disposable local cluster; no production URL accepted','checks':{},'started_at':datetime.now(timezone.utc).isoformat()}
    source_paths=sorted((ROOT/'backend').rglob('*.py'))+[Path(__file__).resolve(),ROOT/'scripts/backup_data.py']
    def source_hash():
        return hashlib.sha256(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_paths},sort_keys=True).encode()).hexdigest()
    report['source_sha256']=source_hash()
    stage='init';started=False
    def command(args,*,env=None,label):
        log=folder/(label+'.log')
        # pg_ctl's server child can inherit stdout. A file avoids waiting for
        # that child's pipe EOF for the entire lifetime of the test cluster.
        with log.open('wb') as stream:
            result=subprocess.run([str(a) for a in args],cwd=ROOT,env=env or environment,
                stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=1800 if label=='pytest' else 120)
        output=log.read_bytes().decode('utf-8',errors='replace')
        for value in redactions:output=output.replace(value,'[redacted]')
        output=re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+','[redacted-token]',output)
        log.write_text(output,encoding='utf-8')
        if result.returncode:raise RuntimeError('Command failed: '+label)
        return output
    def connect(db='postgres',role='bootstrap',*,autocommit=False):
        return psycopg.connect(host='127.0.0.1',port=port,dbname=db,user='audit_bootstrap' if role=='bootstrap' else (owner if role=='owner' else app),
            password=passwords[role],autocommit=autocommit,connect_timeout=3)
    def url(db,role):
        return 'postgresql+psycopg://'+(owner if role=='owner' else app)+':'+passwords[role]+'@127.0.0.1:'+str(port)+'/'+db
    def create_database(name):
        if not name.startswith('lianban_audit_') or not name.endswith(identifier):raise RuntimeError('Unsafe database name')
        with connect(autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(owner)))
            conn.execute(sql.SQL('ALTER DATABASE {} SET lianban.audit_nonce TO {}').format(sql.Identifier(name),sql.Literal(nonce)))
        with connect(name,'owner') as conn:
            conn.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
    def grant_runtime(name):
        with connect(name,'owner') as conn:
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(app)))
            tables=conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version'").fetchall()
            for (table,) in tables:
                conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE {} TO {}').format(sql.Identifier(table),sql.Identifier(app)))
            conn.execute(sql.SQL('GRANT SELECT ON TABLE alembic_version TO {}').format(sql.Identifier(app)))
            conn.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(app)))
    def migrate(name,target,label):
        command([sys.executable,'-m','alembic','upgrade',target],env={**environment,'DATABASE_URL':url(name,'owner')},label=label)
    def snapshot(name):
        with connect(name,'owner') as conn:
            tables=conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
            result={}
            for (table,) in tables:
                rows=conn.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))).fetchall()
                normalized=sorted(json.dumps(row,ensure_ascii=False,default=str,sort_keys=True) for row in rows)
                columns=conn.execute("SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",(table,)).fetchall()
                constraints=conn.execute("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=%s::regclass ORDER BY conname",(table,)).fetchall()
                indexes=conn.execute("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=%s ORDER BY indexname",(table,)).fetchall()
                schema=json.dumps([columns,constraints,indexes],default=str,sort_keys=True)
                result[table]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(normalized).encode()).hexdigest(),
                    'schema_sha256':hashlib.sha256(schema.encode()).hexdigest()}
            return result
    def dump(name,label):
        target=folder/(label+'.dump')
        command([binary/'pg_dump.exe','-h','127.0.0.1','-p',port,'-U',owner,'-d',name,'-Fc','--no-owner','--no-acl','-f',target],
            env={**environment,'PGPASSWORD':passwords['owner']},label=label)
        return target
    def restore(name,backup,label):
        create_database(name)
        command([binary/'pg_restore.exe','-h','127.0.0.1','-p',port,'-U',owner,'-d',name,'--no-owner','--no-acl','--exit-on-error',backup],
            env={**environment,'PGPASSWORD':passwords['owner']},label=label)
    try:
        pwfile=folder/'init-password'
        pwfile.write_text(passwords['bootstrap']+'\n',encoding='utf-8')
        command([binary/'initdb.exe','-D',data,'-U','audit_bootstrap','--encoding=UTF8','--locale=C',
            '--auth-host=scram-sha-256','--auth-local=scram-sha-256','--pwfile='+str(pwfile)],label='initdb')
        pwfile.unlink()
        with (data/'postgresql.conf').open('a',encoding='utf-8') as stream:
            stream.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nmax_connections=30\nshared_buffers='64MB'\nlog_statement='none'\nlog_min_error_statement='panic'\n")
        command([binary/'pg_ctl.exe','-D',data,'-l',folder/'postgres.log','-w','-t','30','start'],label='start')
        started=True
        with connect(autocommit=True) as conn:
            for name,key in ((owner,'owner'),(app,'app')):
                conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Identifier(name),sql.Literal(passwords[key])))
        create_database(database)
        stage='migration-v1';migrate(database,'0001_accounts','migrate-v1')
        legacy_user=str(uuid4())
        with connect(database,'owner') as conn:
            conn.execute('INSERT INTO users(id,email,display_name,role,active,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
                (legacy_user,'legacy-fixture@example.test','合成旧用户','user',True,datetime.now(timezone.utc)))
            conn.execute('INSERT INTO user_records(user_id,id,kind,payload) VALUES(%s,%s,%s,%s)',
                (legacy_user,'legacy-profile','profile',Jsonb({'age':28,'weight_kg':70,'note':'synthetic-legacy-preserve'})))
        legacy=snapshot(database);legacy_backup=dump(database,'legacy-backup')
        stage='migration-head';migrate(database,'head','migrate-head')
        latest=snapshot(database)
        assert all(latest[table]==value for table,value in legacy.items() if table!='alembic_version')
        assert {'health_measurements','research_records','knowledge_chunks'}<=latest.keys()
        report['checks']['migration_0001_to_0003_preserves_old_rows']=True
        before=snapshot(database);migrate(database,'head','migrate-head-again');assert before==snapshot(database)
        report['checks']['repeat_upgrade_is_noop']=True
        grant_runtime(database)
        stage='runtime-permissions'
        with connect(database,'app',autocommit=True) as conn:
            assert conn.execute('SELECT current_database()').fetchone()[0]==database
            assert conn.execute('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()==(False,False,False)
            for text in ('CREATE TABLE forbidden_probe(id int)','ALTER TABLE user_records ADD COLUMN forbidden_probe int',
                'SELECT rolpassword FROM pg_authid',"UPDATE alembic_version SET version_num='0001_accounts'"):
                try:conn.execute(text)
                except psycopg.errors.InsufficientPrivilege:continue
                raise AssertionError('Runtime role had unexpected privileges')
            assert conn.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')").fetchone()[0] is False
            assert conn.execute('SHOW listen_addresses').fetchone()[0]=='127.0.0.1'
        report['checks']['runtime_dml_only_no_ddl_roles_or_auth_catalog']=True
        report['pgvector']='not_installed; optional exact JSON/NumPy branch, not a pgvector acceptance'
        stage='pytest'
        if test_scope!='none':
            files=['backend','tests'] if test_scope=='all' else ['backend/test_auth.py','backend/test_privacy_lifecycle.py','backend/test_context_consent_audit.py']
            output=command([sys.executable,'-m','pytest',*files,'-q','--tb=short'],env={**environment,'DATABASE_URL':url(database,'app')},label='pytest')
            summary=re.findall(r'\d+ passed[^\r\n]*',output)
            report['pytest_summary']=summary[-1] if summary else 'See pytest.log'
            print(report['pytest_summary'],flush=True)
        stage='backup-restore'
        final=snapshot(database);backup=dump(database,'head-backup')
        restored='lianban_audit_restore_'+identifier
        restore(restored,backup,'head-restore');assert snapshot(restored)==final
        grant_runtime(restored)
        with connect(restored,'app') as conn:
            # Exercise restored grants and an identity/sequence-backed insert;
            # rollback keeps the comparison snapshot unchanged.
            restored_user=conn.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchone()
            if restored_user:restored_user=restored_user[0]
            else:
                restored_user=str(uuid4())
                conn.execute('INSERT INTO users(id,email,display_name,role,active,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
                    (restored_user,'restore-probe@example.test','合成恢复探针','user',True,datetime.now(timezone.utc)))
            conn.execute('INSERT INTO user_records(user_id,id,kind,payload) VALUES(%s,%s,%s,%s)',
                (restored_user,'restore-runtime-probe','profile',Jsonb({'synthetic':True})))
            conn.rollback()
        report['checks']['head_backup_restore_rows_and_schema_match']=True
        stage='production-backup-utility'
        with connect(database,'app') as guard:
            guard.execute('LOCK TABLE users IN EXCLUSIVE MODE')
            with connect(database,'app') as reader:
                reader.execute('SELECT count(*) FROM users').fetchone()
            try:
                with connect(database,'app') as writer:
                    writer.execute("SET LOCAL lock_timeout='100ms'")
                    writer.execute('SELECT id FROM users FOR UPDATE')
            except psycopg.errors.LockNotAvailable:pass
            else:raise AssertionError('Backup lock failed to block private user-lock mutations')
        report['checks']['backup_lock_allows_reads_blocks_private_mutations']=True
        app_data=folder/'backup-app-data';(app_data/'uploads').mkdir(parents=True)
        (app_data/'uploads'/'synthetic.txt').write_text('synthetic-media',encoding='utf-8')
        command([sys.executable,ROOT/'scripts/backup_data.py','--data-dir',app_data,'--backup-dir',folder/'utility-backups'],
            env={**environment,'PATH':str(binary)+os.pathsep+environment.get('PATH',''),'DATABASE_URL':url(database,'app')},label='backup-utility')
        archives=list((folder/'utility-backups').glob('*.tar.gz'));assert len(archives)==1
        with tarfile.open(archives[0],'r:gz') as archive:
            assert set(archive.getnames())=={'database.dump','uploads/synthetic.txt'}
            assert archive.extractfile('uploads/synthetic.txt').read()==b'synthetic-media'
            utility_dump=folder/'utility.dump';utility_dump.write_bytes(archive.extractfile('database.dump').read())
        utility_db='lianban_audit_utility_'+identifier
        restore(utility_db,utility_dump,'utility-restore');assert snapshot(utility_db)==final
        report['checks']['application_backup_utility_database_and_media_restore']=True
        rollback='lianban_audit_rollback_'+identifier
        restore(rollback,legacy_backup,'legacy-restore');assert snapshot(rollback)==legacy
        migrate(rollback,'head','legacy-restored-upgrade')
        report['checks']['verified_v1_backup_can_restore_and_upgrade_again']=True
        report['databases']=[database,restored,rollback,utility_db]
        assert source_hash()==report['source_sha256'],'Sources changed during acceptance'
        report['passed']=True
    except Exception as exc:
        report.update(passed=False,failed_stage=stage,error_type=type(exc).__name__)
        print('PostgreSQL acceptance failed at '+stage+'; inspect the redacted local logs.',flush=True)
    finally:
        if started or (data/'postmaster.pid').exists():
            try:
                command([binary/'pg_ctl.exe','-D',data,'-w','-t','20','-m','fast','stop'],label='stop')
                report['cluster_stopped']=True
            except Exception:report['cluster_stopped']=False
        if (folder/'init-password').exists():(folder/'init-password').unlink()
        # Also sanitize output when a child timed out before command() could
        # reach its normal log cleanup path.
        for log in folder.glob('*.log'):
            output=log.read_bytes().decode('utf-8',errors='replace')
            for value in redactions:output=output.replace(value,'[redacted]')
            output=re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+','[redacted-token]',output)
            log.write_text(output,encoding='utf-8')
        try:
            import redis
            cache=redis.Redis.from_url(environment['REDIS_URL'],socket_connect_timeout=2,socket_timeout=2)
            keys=list(cache.scan_iter(match=environment['REDIS_CACHE_NAMESPACE']+':*',count=100))
            if keys:cache.unlink(*keys)
            report['test_cache_namespace_cleaned']=True
        except Exception:report['test_cache_namespace_cleaned']=False
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Report: '+str(folder/'report.json'),flush=True)
    return 0 if report.get('passed') and report.get('cluster_stopped') else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tests',choices=('all','privacy','none'),default='all')
    sys.exit(run(parser.parse_args().tests))
