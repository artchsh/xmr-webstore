# Quickstart (Beginner Friendly)

This guide assumes:

- you can run terminal commands
- Docker is installed
- your server is reachable from internet

## 1) Prepare files

In project folder:

```bash
cp .env.example .env
```

## 2) Fill minimum `.env` values

Edit `.env` and set at least:

- `SHOP_DOMAIN` (example: `shop.example.com`)
- `ACME_EMAIL`
- `WEB_SESSION_SECRET`
- `ADMIN_SESSION_SECRET`
- `DOWNLOAD_TOKEN_SECRET`
- `WALLET_RPC_PASSWORD`
- `WALLET_PASSWORD`
- `ADMIN_PASSWORD`
- `MONERO_REMOTE_NODE`

Use long random values for secrets.

## 3) Start stack

```bash
docker compose up -d --build
```

## 4) Check health

```bash
curl -k https://<SHOP_DOMAIN>/health
curl http://127.0.0.1:<ADMIN_LOCAL_PORT>/health
```

Expected: both return `{"status":"ok"}`.

## 5) First admin login

Open admin URL locally on server:

- `http://127.0.0.1:<ADMIN_LOCAL_PORT>`

If remote, use SSH tunnel from your laptop:

```bash
ssh -L 8081:127.0.0.1:8081 user@your-server
```

Then open `http://127.0.0.1:8081`.

## 6) Add first product

- Admin -> Products -> Create product
- Upload digital file
- (optional) upload product image
- Save

Now product appears on storefront.
