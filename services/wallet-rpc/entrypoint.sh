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

TOR_HOST="${TOR_SOCKS_HOST:-tor}"
TOR_PORT="${TOR_SOCKS_PORT:-9050}"
TOR_ADDR="$(getent hosts "${TOR_HOST}" | head -n 1 | cut -d ' ' -f1 || true)"

USE_TORSOCKS=1
if [ "${TOR_SOCKS_DISABLED:-false}" = "true" ]; then
  echo "TOR_SOCKS_DISABLED=true; starting wallet-rpc without torsocks"
  USE_TORSOCKS=0
elif [ -z "${TOR_ADDR}" ]; then
  echo "Warning: could not resolve TOR_SOCKS_HOST=${TOR_HOST}; starting wallet-rpc without torsocks"
  USE_TORSOCKS=0
else
  cat > /etc/tor/torsocks.conf <<EOF
TorAddress ${TOR_ADDR}
TorPort ${TOR_PORT}
OnionAddrRange 127.42.42.0/24
EOF
fi

if [ -n "${MONERO_REMOTE_NODES:-}" ]; then
  FIRST_NODE="$(printf '%s' "${MONERO_REMOTE_NODES}" | cut -d ',' -f1 | xargs)"
  if [ -n "${FIRST_NODE}" ]; then
    MONERO_REMOTE_NODE="${MONERO_REMOTE_NODE:-${FIRST_NODE}}"
  fi
fi

if [ -z "${MONERO_REMOTE_NODE:-}" ]; then
  echo "MONERO_REMOTE_NODE is required (example: node.moneroworld.com:18089)"
  echo "You may also set MONERO_REMOTE_NODES as a comma-separated fallback list."
  exit 1
fi

MONERO_NETWORK="${MONERO_NETWORK:-mainnet}"
NETWORK_FLAG=""
case "${MONERO_NETWORK}" in
  mainnet)
    NETWORK_FLAG=""
    ;;
  stagenet)
    NETWORK_FLAG="--stagenet"
    ;;
  testnet)
    NETWORK_FLAG="--testnet"
    ;;
  *)
    echo "Unsupported MONERO_NETWORK='${MONERO_NETWORK}'. Use mainnet, stagenet, or testnet."
    exit 1
    ;;
esac

if [ -z "${WALLET_RPC_USERNAME:-}" ] || [ -z "${WALLET_RPC_PASSWORD:-}" ]; then
  echo "WALLET_RPC_USERNAME and WALLET_RPC_PASSWORD are required"
  exit 1
fi

set -- "${MONERO_INSTALL_DIR}/monero-wallet-rpc" \
  --rpc-bind-ip "${WALLET_RPC_BIND_IP:-0.0.0.0}" \
  --rpc-bind-port "${WALLET_RPC_PORT:-18083}" \
  --rpc-login "${WALLET_RPC_USERNAME}:${WALLET_RPC_PASSWORD}" \
  --wallet-dir "${WALLET_DIR:-/wallet}" \
  --daemon-address "${MONERO_REMOTE_NODE}" \
  --trusted-daemon \
  --confirm-external-bind \
  --non-interactive \
  --log-level "${WALLET_LOG_LEVEL:-0}"

if [ -n "${NETWORK_FLAG}" ]; then
  set -- "$@" "${NETWORK_FLAG}"
fi

if [ "${USE_TORSOCKS}" = "1" ]; then
  exec torsocks "$@"
else
  exec "$@"
fi
