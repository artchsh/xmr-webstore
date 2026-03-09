#!/usr/bin/env sh
set -eu

echo "Stopping any currently running compose stack..."
docker compose down

echo "Starting staging stack (docker-compose.yml + docker-compose.staging.yml)..."
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml up -d --build

echo "Done."
echo "Storefront: https://localhost:8443"
echo "Admin (local): http://127.0.0.1:${ADMIN_LOCAL_PORT:-18081}"
