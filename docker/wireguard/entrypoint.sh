#!/bin/bash
set -euo pipefail

if [[ ! -s /config/client.conf ]]; then
    echo 'Missing WireGuard configuration: /config/client.conf' >&2
    exit 1
fi

umask 077
mkdir -p /run/wireguard
# Docker keeps its own DNS. The tunnel carries only the configured AllowedIPs.
# Keep the original config read-only; never print its private keys.
sed '/^[[:space:]]*DNS[[:space:]]*=/d' /config/client.conf > /run/wireguard/wg0.conf
export WG_QUICK_USERSPACE_IMPLEMENTATION=wireguard-go

cleanup() {
    wg-quick down /run/wireguard/wg0.conf || true
    rm -f /run/wireguard/wg0.conf
}
trap cleanup EXIT
trap 'exit 0' TERM INT
wg-quick up /run/wireguard/wg0.conf
echo 'WireGuard interface is ready (a handshake is checked separately with wg show).'
ip -4 address show dev wg0

while true; do
    sleep 3600 &
    wait $! || true
done
