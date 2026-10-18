#!/usr/bin/env bash
# Replace the private download only after a complete, verified transfer.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
source_apk=${1:?Pass uploaded APK path}
expected_sha=${2:?Pass verified APK SHA256}
[[ "$source_apk" == /tmp/lianban-private-test-*.apk && -f "$source_apk" ]] || exit 1
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || exit 1
actual_sha=$(sha256sum "$source_apk")
[[ "${actual_sha%% *}" == "$expected_sha" ]] || { echo 'APK transfer checksum mismatch.' >&2; exit 1; }
target=/var/lib/liftlab/private-test/lianban-test.apk
[[ -f "$target" ]] || { echo 'Private download must already be configured.' >&2; exit 1; }
install -m 0644 "$source_apk" "$target.next"
mv -f -- "$target.next" "$target"
echo "Published private APK SHA256 $expected_sha"
