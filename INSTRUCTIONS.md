# Deployment Instructions

For beginner-first setup guides, also see:

- `docs/quickstart.md`
- `docs/vps-dns.md`
- `docs/configuration.md`

This project supports three operating modes:

1. Production (`docker-compose.yml`)
2. Stagenet testing (`docker-compose.yml` + `docker-compose.staging.yml`)
3. Local development (same services, local-safe settings)

## 1) Production Environment

Use only the default compose file (`docker-compose.yml`).

### Steps

1. Create env file:

```bash
cp .env.example .env
```

2. Edit `.env` with real values:

- set `SHOP_DOMAIN` and `ACME_EMAIL`
- set long random secrets:
  - `WEB_SESSION_SECRET`
  - `ADMIN_SESSION_SECRET`
  - `DOWNLOAD_TOKEN_SECRET`
- set strong passwords:
  - `WALLET_RPC_PASSWORD`
  - `WALLET_PASSWORD`
  - `ADMIN_PASSWORD` (or `ADMIN_PASSWORD_HASH`)
- set mainnet remote node:
  - `MONERO_NETWORK=mainnet`
  - `MONERO_REMOTE_NODE=<healthy-mainnet-node:18089>`
  - optional fallback list:
    - `MONERO_REMOTE_NODES=node1:18089,node2:18089,node3:18089`
- keep Tor on in production:
  - `TOR_SOCKS_DISABLED=false`
- set HTTPS cookie mode:
  - `COOKIE_SECURE=true`
- optional branding defaults in env:
  - `SHOP_NAME`
  - `SHOP_OWNER`
  - `SHOP_LOGO_URL`

3. Start production stack:

```bash
docker compose up -d --build
```

4. Verify:

```bash
curl -k https://<SHOP_DOMAIN>/health
curl http://127.0.0.1:<ADMIN_LOCAL_PORT>/health
```

## 2) Stagenet Wallet Environment

Use the staging override file to switch network and ports without touching production compose.

### Steps

1. Create staging env file:

```bash
cp .env.staging.example .env.staging
```

2. Edit `.env.staging`:

- `MONERO_NETWORK=stagenet`
- `MONERO_REMOTE_NODE=<healthy-stagenet-node:38081>`
- optional fallback list:
  - `MONERO_REMOTE_NODES=stagenet-node-a:38081,stagenet-node-b:38081`
- staging secrets/passwords

3. Stop existing stack:

```bash
docker compose down
```

4. Start staging stack:

```bash
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml up -d --build
```

5. Access staging endpoints:

- storefront: `https://localhost:8443`
- admin: `http://127.0.0.1:18081`

6. Stop staging and return to production:

```bash
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml down
docker compose up -d --build
```

## 3) Local Development Environment

For local development without production DNS/TLS requirements:

1. Use a local `.env` with:

- `SHOP_DOMAIN=localhost`
- `COOKIE_SECURE=false`
- `ADMIN_LOCAL_PORT=8081`
- `MONERO_NETWORK=mainnet` or `stagenet` as needed
- `MONERO_REMOTE_NODES` can be used in all environments for daemon failover attempts

2. Start dev stack:

```bash
docker compose up -d --build
```

3. Access:

- storefront: `https://localhost`
- admin: `http://127.0.0.1:8081`

## Notes on Switching

- `docker-compose.yml` is the production default.
- `docker-compose.staging.yml` is an override for stagenet and safer local testing ports.
- Use `--env-file` so variable interpolation (like port bindings) comes from the intended env file.

## Product Images

- Admin product form supports either:
  - image URL (`http://` or `https://`)
  - uploaded image file
- Uploaded images are stored in `PRODUCT_IMAGES_DIR` (default `/data/product_images`).
- Storefront serves uploaded images from `/media/product/<filename>`.

## Shop Branding

- Use admin `Settings` page to configure:
  - shop name
  - shop owner
  - logo URL or uploaded logo
- Uploaded branding assets are stored in `BRANDING_ASSETS_DIR` (default `/data/branding`).
- Uploaded logo is served from `/media/branding/<filename>`.
- Current MVP uses the uploaded/logo URL directly as favicon.
- Automatic multi-size icon generation (`.ico`, PWA icon set, manifest) is intentionally not included yet.
