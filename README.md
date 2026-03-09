# xmr-webstore

Privacy-first self-hosted digital goods shop that accepts Monero.

Built for one seller, small operations, and simple deployment.

## What this project does

- public storefront (no customer accounts, no email)
- separate admin panel for products/orders/settings
- Monero checkout with `monero-wallet-rpc`
- SQLite database (single file)
- Caddy HTTPS reverse proxy
- optional stagenet mode for safer payment testing

## 10-minute quick start

1. Copy environment template:

```bash
cp .env.example .env
```

2. Edit `.env`:

- set `SHOP_DOMAIN` to your domain
- set `ACME_EMAIL` to your email (for TLS certs)
- set strong secrets/passwords (`WEB_SESSION_SECRET`, `ADMIN_SESSION_SECRET`, `DOWNLOAD_TOKEN_SECRET`, `WALLET_RPC_PASSWORD`, `ADMIN_PASSWORD`)
- set Monero node (`MONERO_REMOTE_NODE`)

3. Start services:

```bash
docker compose up -d --build
```

4. Open:

- storefront: `https://<SHOP_DOMAIN>`
- admin: `http://127.0.0.1:<ADMIN_LOCAL_PORT>`

Default admin is host-local only (not public).

## Recommended VPS (simple baseline)

- OS: Ubuntu 22.04 or 24.04 LTS
- CPU: 2 vCPU recommended (1 vCPU minimum)
- RAM: 4 GB recommended (2 GB minimum)
- Disk: 40 GB SSD recommended (25 GB minimum)
- Open ports: `80`, `443`

## Documentation

- setup modes (production/staging/development): `INSTRUCTIONS.md`
- beginner quickstart: `docs/quickstart.md`
- VPS + DNS walkthrough: `docs/vps-dns.md`
- env/config explanation: `docs/configuration.md`
- architecture notes: `docs/architecture.md`
- testing guide: `docs/testing.md`

## Common commands

- start: `docker compose up -d --build`
- stop: `docker compose down`
- logs: `docker compose logs -f`
- staging: `docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml up -d --build`
