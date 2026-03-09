#!/bin/sh
set -eu

MONERO_INSTALL_DIR="/opt/monero"
MONERO_DOWNLOAD_URL="${MONERO_CLI_DOWNLOAD_URL:-https://downloads.getmonero.org/cli/linux64}"

mkdir -p "${MONERO_INSTALL_DIR}" "${WALLET_DIR:-/wallet}"

if [ ! -x "${MONERO_INSTALL_DIR}/monero-wallet-rpc" ]; then
  echo "Downloading Monero CLI bundle from ${MONERO_DOWNLOAD_URL}"
  curl -L --fail --output /tmp/monero.tar.bz2 "${MONERO_DOWNLOAD_URL}"
  tar -xjf /tmp/monero.tar.bz2 -C "${MONERO_INSTALL_DIR}" --strip-components=1
  rm -f /tmp/monero.tar.bz2
fi

cat > /etc/tor/torsocks.conf <<EOF
TorAddress ${TOR_SOCKS_HOST:-tor}
TorPort ${TOR_SOCKS_PORT:-9050}
OnionAddrRange 127.42.42.0/24
EOF

if [ -z "${MONERO_REMOTE_NODE:-}" ]; then
  echo "MONERO_REMOTE_NODE is required (example: node.moneroworld.com:18089)"
  exit 1
fi

if [ -z "${WALLET_RPC_USERNAME:-}" ] || [ -z "${WALLET_RPC_PASSWORD:-}" ]; then
  echo "WALLET_RPC_USERNAME and WALLET_RPC_PASSWORD are required"
  exit 1
fi

exec torsocks "${MONERO_INSTALL_DIR}/monero-wallet-rpc" \
  --rpc-bind-ip "${WALLET_RPC_BIND_IP:-0.0.0.0}" \
  --rpc-bind-port "${WALLET_RPC_PORT:-18083}" \
  --rpc-login "${WALLET_RPC_USERNAME}:${WALLET_RPC_PASSWORD}" \
  --wallet-dir "${WALLET_DIR:-/wallet}" \
  --daemon-address "${MONERO_REMOTE_NODE}" \
  --trusted-daemon \
  --confirm-external-bind \
  --non-interactive \
  --log-level "${WALLET_LOG_LEVEL:-0}"
