# xmr-webstore MVP v1 Architecture

## Phase 1: Architecture and assumptions

- Goal: one-seller, self-hosted digital goods shop with Monero-only checkout.
- Privacy baseline: no accounts, no email, no third-party scripts, no external analytics.
- UX baseline: server-rendered HTML forms, no JavaScript required for critical flows.
- Infra baseline: simple Docker Compose stack, SQLite file storage, one reverse proxy.
- Payment baseline: monero-wallet-rpc with subaddresses, remote public Monero node, outbound traffic routed through Tor SOCKS5.

## Runtime containers (exactly 5)

1. `webshop` (FastAPI SSR public shop)
2. `admin` (FastAPI SSR admin panel, separate runtime)
3. `wallet-rpc` (monero-wallet-rpc internal only)
4. `caddy` (public HTTPS reverse proxy)
5. `tor` (SOCKS5 proxy for outbound privacy)

## Network and exposure model

- Public internet:
  - Caddy (`:80`, `:443`) -> webshop only.
- Host-local only:
  - Admin bound to `127.0.0.1:${ADMIN_LOCAL_PORT}` by default.
- Internal Docker network (`private_net`, `internal: true`):
  - webshop <-> wallet-rpc
  - admin <-> wallet-rpc
  - wallet-rpc -> tor (SOCKS5)

`wallet-rpc` is never exposed on host ports.

## Data model summary

- `products`: catalog + delivery metadata
- `orders`: public token + status lifecycle + payment summary
- `order_items`: immutable snapshots for historical integrity
- `payment_requests`: one payment target per order (subaddress/index)
- `delivery_events`: operational audit trail (order completion/download)
- `analytics_events`: minimal server-side event log
- `admin_users`: admin auth credentials (hashed password)

## Order lifecycle

- `pending_payment`
- `waiting_confirmations`
- `completed`
- `expired`
- `cancelled`

## Security controls included

- CSRF tokens for all POST forms (public + admin)
- admin session auth with PBKDF2 password hashing
- strict server-side validation for product and cart inputs
- signed short-lived download links for paid order files
- digital goods file path validation to block traversal
- wallet-rpc credentials only in internal services/env vars

## Explicitly excluded from MVP v1

- customer accounts or customer authentication
- email delivery or email notifications
- JavaScript SPA/API checkout architecture
- third-party analytics, tracking pixels, external fonts
- non-Monero payment rails
- multi-vendor marketplace features
- PostgreSQL/Redis/Celery/Kubernetes complexity
