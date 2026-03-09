#!/usr/bin/env sh
set -eu

echo "Stopping any currently running compose stack..."
docker compose down

echo "Starting production stack (docker-compose.yml)..."
docker compose up -d --build

echo "Done."
echo "Storefront: https://${SHOP_DOMAIN:-localhost}"
echo "Admin (local): http://127.0.0.1:${ADMIN_LOCAL_PORT:-8081}"
