# xmr-webstore (MVP v1)

Privacy-first, self-hostable Monero digital goods webshop for a single seller.

- backend: Python + FastAPI
- rendering: SSR Jinja templates
- database: SQLite
- reverse proxy: Caddy
- payment: monero-wallet-rpc (remote public node via Tor SOCKS5)
- frontend: no JavaScript required for critical flow

This repository intentionally keeps setup and maintenance simple for a solo operator.

## What is included

- public storefront service (`webshop`) with:
  - product catalog
  - cookie-session cart
  - Monero checkout + payment instructions
  - order receipt by public order token
  - paid download links with short-lived signatures
- separate admin service (`admin`) with:
  - login
  - product CRUD (create/edit/archive/delete)
  - file upload or file path registration for digital goods
  - order list/detail and manual cancel
  - wallet balance/address view
  - basic privacy-preserving analytics
- wallet integration:
  - create subaddresses per order
  - poll and reconcile incoming transfers
  - transition order states based on confirmations
- infrastructure:
  - 5-container Docker Compose stack
  - Caddy public TLS reverse proxy
  - Tor SOCKS5 container for outbound wallet privacy

## Intentionally excluded from MVP v1

- customer accounts, login, or profiles
- customer email collection or email delivery
- third-party analytics or tracking scripts
- JavaScript SPA/API-based checkout
- multi-vendor marketplace features
- payment methods other than Monero
- PostgreSQL, Redis, Celery, Kubernetes

## Project structure

```text
.
├── Caddyfile
├── docker-compose.yml
├── requirements.txt
├── common/
│   ├── analytics.py
│   ├── config.py
│   ├── db.py
│   ├── migrations.py
│   ├── order_poller.py
│   ├── security.py
│   ├── utils.py
│   └── wallet_rpc.py
├── docs/
│   └── architecture.md
└── services/
    ├── admin/
    │   ├── Dockerfile
    │   ├── main.py
    │   ├── static/
    │   └── templates/
    ├── tor/
    │   ├── Dockerfile
    │   └── torrc
    ├── wallet-rpc/
    │   ├── Dockerfile
    │   └── entrypoint.sh
    └── webshop/
        ├── Dockerfile
        ├── main.py
        ├── static/
        └── templates/
```

## Quick start

1) Copy env file and set strong secrets.

```bash
cp .env.example .env
```

2) Edit `.env`:

- set `SHOP_DOMAIN` and `ACME_EMAIL` for TLS
- set strong values for:
  - `WEB_SESSION_SECRET`
  - `ADMIN_SESSION_SECRET`
  - `DOWNLOAD_TOKEN_SECRET`
  - `WALLET_RPC_PASSWORD`
  - `ADMIN_PASSWORD`
- set remote node in `MONERO_REMOTE_NODE`
- set wallet file/password (`WALLET_FILE`, `WALLET_PASSWORD`)
- set `COOKIE_SECURE=true` when both shop/admin are behind HTTPS

3) Start services.

```bash
docker compose up -d --build
```

4) Access services.

- storefront: `https://<SHOP_DOMAIN>`
- admin (local only by default): `http://127.0.0.1:${ADMIN_LOCAL_PORT}`

If admin is remote, use SSH tunnel instead of exposing it publicly.

```bash
ssh -L 8081:127.0.0.1:8081 user@server
```

Then open `http://127.0.0.1:8081` locally.

## Payment flow summary

1. customer browses and adds product to cart
2. checkout creates order and Monero subaddress
3. order page displays payment amount + subaddress
4. background poller checks wallet incoming transfers
5. order transitions to `waiting_confirmations` then `completed`
6. receipt page exposes download links only after completion

## SQLite schema and migration strategy

- Schema is defined in `common/migrations.py`.
- Migrations are applied at startup using `PRAGMA user_version`.
- Both `webshop` and `admin` can safely run startup migrations.
- Database path defaults to `/data/webshop.db` via shared Docker volume.

## Security notes

- Admin and webshop are separate containers.
- wallet-rpc is internal only and not published to host/network edge.
- CSRF checks on POST forms in both services.
- Admin passwords are PBKDF2-hashed in database.
- Download access uses HMAC signatures and expiry timestamps.
- File paths are restricted to configured digital goods directory.
- Minimal data collection: no customer identity fields by default.

## Operational notes

- Put digital goods in the shared data volume path (`/data/digital_goods` in containers).
- Use admin product form to upload or register existing files.
- Order status updates depend on wallet-rpc + remote node availability.
- If wallet setup should be automatic on first boot, set `WALLET_AUTO_CREATE=true`.

## Development

Run locally with Compose:

```bash
docker compose up --build
```

Stop services:

```bash
docker compose down
```
