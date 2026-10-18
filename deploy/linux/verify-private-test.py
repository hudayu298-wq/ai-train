"""Verify the private HTTPS entry without reading passwords or changing user data."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from cryptography import x509

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host', required=True)
parser.add_argument('--ip', required=True)
parser.add_argument('--apk-sha256', required=True)
parser.add_argument('--apk-size', required=True, type=int)
args = parser.parse_args()

def command(*parts):
    return subprocess.check_output(parts, timeout=45)

status = json.loads(command('tailscale', 'status', '--json'))
config = json.loads(command('tailscale', 'serve', 'status', '--json'))
assert status['BackendState'] == 'Running'
assert not status['TUN'], 'Expected userspace networking to avoid the cloud DNS conflict'
assert args.host == status['Self']['DNSName'].rstrip('.')
assert not config.get('AllowFunnel'), 'The private test must not enable public Funnel'
handlers = config['Web'][args.host + ':443']['Handlers']
assert handlers['/']['Proxy'] == 'http://127.0.0.1:8000'
apk = Path('/var/lib/liftlab/private-test/lianban-test.apk')
assert handlers['/downloads/lianban-test.apk']['Path'] == str(apk)
assert apk.stat().st_size == args.apk_size
assert hashlib.sha256(apk.read_bytes()).hexdigest() == args.apk_sha256

curl = ['curl', '--silent', '--show-error', '--socks5', '127.0.0.1:1055',
        '--connect-timeout', '15', '--max-time', '30', '--resolve',
        args.host + ':443:' + args.ip]
base = 'https://' + args.host
health = json.loads(command(*curl, '--fail', base + '/api/health'))
assert health['status'] == 'ok'
code = command(*curl, '-o', '/dev/null', '-w', '%{http_code}', base + '/api/profile').decode()
assert code == '401', 'Protected data must require application authentication'
headers = command(*curl, '--fail', '--head', base + '/downloads/lianban-test.apk').decode()
parsed = dict(line.split(': ', 1) for line in headers.lower().splitlines() if ': ' in line)
assert int(parsed['content-length']) == args.apk_size
assert 'application/vnd.android.package-archive' in parsed['content-type']
assert command(*curl, '--fail', '--range', '0-3', base + '/downloads/lianban-test.apk') == b'PK\x03\x04'
certificate = x509.load_pem_x509_certificate(
    (Path('/var/lib/tailscale/certs') / (args.host + '.crt')).read_bytes())
assert args.host in certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
assert command('systemctl', 'is-active', 'liftlab').strip() == b'active'
assert command('systemctl', 'is-enabled', 'tailscaled').strip() == b'enabled'
# Caddy is deliberately masked until the public deployment is ready.
caddy = subprocess.run(['systemctl', 'is-enabled', 'caddy'], capture_output=True)
assert caddy.stdout.strip() == b'masked'
listeners = command('ss', '-lntH').decode()
for line in listeners.splitlines():
    endpoint = line.split()[3]
    if endpoint.endswith((':8000', ':5432', ':1055')):
        assert endpoint.startswith(('127.', '[::1]')), 'Unexpected public backend, DB or proxy listener'

report = {'private_https_verified': True, 'health_ok': True, 'unauthorized_status': int(code),
          'api_base': base, 'apk_download_url': base + '/downloads/lianban-test.apk',
          'apk_size': args.apk_size, 'apk_sha256': args.apk_sha256,
          'apk_range_download_verified': True, 'userspace_networking': True,
          'public_funnel_enabled': False, 'public_caddy_service': 'masked',
          'certificate_issuer': certificate.issuer.rfc4514_string(),
          'certificate_not_after_utc': certificate.not_valid_after_utc.isoformat(),
          'mobile_installation_verified': False}
Path('/var/lib/liftlab/private-test-verification.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
