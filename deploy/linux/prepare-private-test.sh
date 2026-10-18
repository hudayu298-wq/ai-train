#!/usr/bin/env bash
# Install the official client; joining the user's tailnet is a separate step.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'This installer targets Ubuntu 24.04.' >&2; exit 1; }
if ! command -v tailscale >/dev/null; then
  task_dir=$(mktemp -d /tmp/lianban-tailscale.XXXXXXXX)
  trap 'rm -f -- "$task_dir/tailscale.gpg" "$task_dir/tailscale.list"; rmdir -- "$task_dir"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --connect-timeout 20 --max-time 90 \
    https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o "$task_dir/tailscale.gpg"
  curl --fail --silent --show-error --location --proto '=https' --connect-timeout 20 --max-time 90 \
    https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list -o "$task_dir/tailscale.list"
  install -m 0644 "$task_dir/tailscale.gpg" /usr/share/keyrings/tailscale-archive-keyring.gpg
  install -m 0644 "$task_dir/tailscale.list" /etc/apt/sources.list.d/tailscale.list
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y tailscale
fi
systemctl enable --now tailscaled.service
tailscale version
echo 'Client ready. Authenticate explicitly, then configure private HTTPS Serve.'
