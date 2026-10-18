#!/usr/bin/env bash
# Only the application and APK are served inside the authenticated tailnet.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
expected_sha=${1:?Pass the verified APK SHA256}
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || exit 1
actual_sha=$(sha256sum /tmp/lianban-private-test-arm64.apk)
[[ "${actual_sha%% *}" == "$expected_sha" ]] || { echo 'APK transfer checksum mismatch.' >&2; exit 1; }

# Huawei's DNS uses 100.125.1.250, within the CGNAT range filtered by Tailscale.
# Userspace mode avoids changing the host routes/firewall or exposing host ports.
# The loopback-only SOCKS endpoint is used for server-side HTTPS verification.
python3 - <<'PY'
from pathlib import Path
import re
p = Path('/etc/default/tailscaled')
text = p.read_text()
desired = '--tun=userspace-networking --socks5-server=127.0.0.1:1055'
match = re.search(r'^FLAGS="([^"]*)"$', text, re.M)
if not match or match.group(1) not in ('', desired):
    raise SystemExit('Unexpected existing Tailscale flags; review before changing them.')
if match.group(1) != desired:
    backup = p.with_name('tailscaled.before-lianban-private-test')
    if not backup.exists():
        backup.write_text(text)
        backup.chmod(0o600)
    p.write_text(text[:match.start()] + 'FLAGS="' + desired + '"' + text[match.end():])
PY
systemctl restart tailscaled.service
resolvectl flush-caches
for attempt in $(seq 1 30); do
  state=$(tailscale status --json | python3 -c 'import sys,json; print(json.load(sys.stdin)["BackendState"])')
  [[ "$state" == Running ]] && break
  sleep 1
done
[[ "$state" == Running ]] || { echo 'Private network is not ready.' >&2; exit 1; }

install -d -m 0755 /var/lib/liftlab/private-test
install -m 0644 /tmp/lianban-private-test-arm64.apk /var/lib/liftlab/private-test/lianban-test.apk
install -m 0700 /tmp/lianban-manage-test-account.py /var/lib/liftlab/manage-test-account.py
tailscale serve --bg http://127.0.0.1:8000
tailscale serve --bg --set-path=/downloads/lianban-test.apk /var/lib/liftlab/private-test/lianban-test.apk
tailscale serve status --json
echo "Private APK installed with SHA256 $expected_sha"
