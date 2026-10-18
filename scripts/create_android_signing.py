"""Create a private, persistent Android release key without exposing passwords."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
ALIAS = 'lianban-release'


def restrict(path, directory=False):
    if os.name == 'nt':
        sid = subprocess.check_output(['powershell', '-NoProfile', '-Command',
            '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], text=True).strip()
        rights = '(OI)(CI)F' if directory else 'F'
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:{rights}'], capture_output=True)
        if result.returncode:
            raise RuntimeError('Unable to protect signing file permissions; generation stopped.')
    else:
        path.chmod(0o700 if directory else 0o600)


def create(keytool):
    directory = Path.home() / '.android/lianban-signing'
    store = directory / 'lianban-release.p12'
    config = ROOT / 'mobile/android/key.properties'
    if store.exists() and config.exists():
        print('Release signing already exists; the key and credentials were preserved.')
        return
    if store.exists() or config.exists():
        raise RuntimeError('Partial existing signing configuration; recover it rather than creating a replacement key.')
    directory.mkdir(parents=True, exist_ok=True)
    restrict(directory, directory=True)
    password = secrets.token_urlsafe(48)
    env = dict(os.environ, LIANBAN_SIGNING_PASSWORD=password)
    command = [str(keytool), '-genkeypair', '-noprompt', '-storetype', 'PKCS12',
        '-keystore', str(store), '-alias', ALIAS, '-keyalg', 'RSA', '-keysize', '3072',
        '-sigalg', 'SHA256withRSA', '-validity', '10000', '-dname', 'CN=Lianban Android Signing',
        '-storepass:env', 'LIANBAN_SIGNING_PASSWORD', '-keypass:env', 'LIANBAN_SIGNING_PASSWORD']
    result = subprocess.run(command, env=env, capture_output=True)
    if result.returncode:
        raise RuntimeError('Key generation failed; no credentials were printed. Inspect the protected signing directory before retrying.')
    restrict(store)
    # Create and protect the empty configuration before writing credentials.
    config.touch(exist_ok=False)
    restrict(config)
    config.write_text(f'storeFile={store.as_posix()}\nstoreType=PKCS12\nkeyAlias={ALIAS}\n'
        f'storePassword={password}\nkeyPassword={password}\n', encoding='ascii')
    public = ROOT / 'docs/assets/filing/android'
    public.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(keytool), '-exportcert', '-keystore', str(store), '-alias', ALIAS,
        '-storepass:env', 'LIANBAN_SIGNING_PASSWORD', '-file', str(public / 'lianban-signing-cert.der')],
        env=env, capture_output=True)
    if result.returncode:
        raise RuntimeError('Public certificate export failed; the private key is preserved.')
    print('Created RSA-3072 release signing key, protected key.properties and public certificate. Passwords were not printed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keytool', type=Path, default=shutil.which('keytool') or Path('C:/Program Files/Java/jdk-17/bin/keytool.exe'))
    arguments = parser.parse_args()
    if not arguments.keytool.is_file():
        raise SystemExit('A JDK keytool executable is required.')
    create(arguments.keytool)
