#!/usr/bin/env bash
# Install and validate Caddy without enabling a public site before filing.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
source_config=${1:?Pass the LiftLab Caddyfile path}
[[ -f "$source_config" ]] || { echo 'Caddyfile not found.' >&2; exit 1; }
if systemctl is-active --quiet caddy.service || systemctl is-active --quiet caddy-api.service; then
  echo 'An existing Caddy service is active; review it before using this preparer.' >&2
  exit 1
fi
# Official packages start the service automatically; block that until public access is ready.
systemctl mask caddy.service caddy-api.service
if ! command -v caddy >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  task_dir=$(mktemp -d /tmp/liftlab-caddy.XXXXXXXX)
  trap 'rm -f -- "$task_dir/gpg.key" "$task_dir/caddy.gpg" "$task_dir/stable.list"; rmdir -- "$task_dir"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --connect-timeout 20 --max-time 90 \
    https://dl.cloudsmith.io/public/caddy/stable/gpg.key -o "$task_dir/gpg.key"
  gpg --batch --dearmor --output "$task_dir/caddy.gpg" "$task_dir/gpg.key"
  curl --fail --silent --show-error --location --proto '=https' --connect-timeout 20 --max-time 90 \
    https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o "$task_dir/stable.list"
  install -m 0644 "$task_dir/caddy.gpg" /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  install -m 0644 "$task_dir/stable.list" /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y caddy
fi
install -d -m 0755 /etc/caddy
install -m 0644 "$source_config" /etc/caddy/liftlab.Caddyfile.pending
caddy fmt --overwrite /etc/caddy/liftlab.Caddyfile.pending
caddy validate --config /etc/caddy/liftlab.Caddyfile.pending --adapter caddyfile
if systemctl is-active --quiet caddy.service || systemctl is-active --quiet caddy-api.service; then
  echo 'Unexpected running Caddy service.' >&2
  exit 1
fi
systemctl is-enabled caddy.service || true
caddy version
echo 'HTTPS prepared and validated; service remains masked. No certificate or public endpoint was activated.'
