# Configuration Reference (Simple)

## Core shop identity

- `SHOP_NAME`: storefront/admin display name
- `SHOP_OWNER`: optional owner label
- `SHOP_LOGO_URL`: optional logo URL

You can also manage branding in Admin -> Settings.

## Domain and TLS

- `SHOP_DOMAIN`: public domain served by Caddy
- `ACME_EMAIL`: email for TLS certificate registration
- `COOKIE_SECURE`: set `true` in HTTPS production

## Database and files

- `DATABASE_PATH`: SQLite file path
- `DIGITAL_GOODS_DIR`: product file storage
- `PRODUCT_IMAGES_DIR`: product image storage
- `BRANDING_ASSETS_DIR`: uploaded logo storage

## Monero wallet settings

- `WALLET_RPC_USERNAME`
- `WALLET_RPC_PASSWORD`
- `WALLET_FILE`
- `WALLET_PASSWORD`
- `WALLET_AUTO_CREATE`
- `MONERO_NETWORK` (`mainnet`, `stagenet`, `testnet`)
- `MONERO_REMOTE_NODE` (primary daemon)
- `MONERO_REMOTE_NODES` (comma-separated fallback nodes)

## Order behavior

- `ORDER_EXPIRY_MINUTES`
- `REQUIRED_CONFIRMATIONS`
- `PAYMENT_POLL_INTERVAL_SECONDS`

## Admin access

- `ADMIN_LOCAL_PORT`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH`
