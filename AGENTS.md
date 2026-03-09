## Current Memory
[.opencode/2026-03-10_MEMORY.md](.opencode/2026-03-10_MEMORY.md)

## Memory Management Rules
"Every time you start a session or are asked to update memory:
1. Look at the file linked under 'Current Memory' — this is always the most recent memory file.
2. Check its date from the filename (YYYY-MM-DD).
3. If that file is more than 7 days old (or none exists), create a brand new dated memory file using today's exact date (YYYY-MM-DD_MEMORY.md) with a fresh full summary of the current project state. Do NOT edit, append to, or touch any existing memory files.
4. Immediately update the 'Current Memory' link at the top of this AGENTS.md to point to the new file.
5. Always use ONLY the linked Current Memory file as your primary context. Ignore older memory files unless the user specifically asks for historical reference."

# Project Bible — xmr-webstore

## Project Overview (what we're building and why)

`xmr-webstore` is a privacy-first, self-hostable Monero digital goods webshop for a single seller.

The product goal is practical and specific:

- deploy quickly on a VPS/local server
- avoid overengineering and external dependencies
- minimize identity collection and tracking
- support non-front-end-heavy operators with simple admin workflows

Core principles:

- privacy first
- simplicity first
- maintainability for solo operators
- deterministic server-rendered flows

## Technical Architecture (detailed breakdown)

### Service topology

The runtime uses five containers:

1. `webshop`: public SSR storefront (FastAPI)
2. `admin`: separate SSR admin panel (FastAPI)
3. `wallet-rpc`: internal Monero wallet RPC service
4. `caddy`: edge reverse proxy + TLS termination
5. `tor`: SOCKS5 proxy for outbound privacy routing

### Data model and persistence

- SQLite as primary datastore
- Key tables:
  - `products`
  - `orders`
  - `order_items`
  - `payment_requests`
  - `delivery_events`
  - `analytics_events`
  - `admin_users`
  - `shop_settings`
- Migrations handled by app startup with `PRAGMA user_version`

### Payments and order lifecycle

- Monero-only via `monero-wallet-rpc`
- One payment subaddress per order
- Polling reconciler updates order/payment status based on incoming transfers and confirmations
- Supported lifecycle states:
  - `pending_payment`
  - `waiting_confirmations`
  - `completed`
  - `expired`
  - `cancelled`

### Wallet node reliability strategy

- Primary remote node: `MONERO_REMOTE_NODE`
- Fallback node list: `MONERO_REMOTE_NODES` (comma-separated)
- Network modes: `mainnet`, `stagenet`, `testnet`
- App-side failover attempts on daemon connection errors

### Frontend/server rendering strategy

- SSR templates with Jinja
- No JavaScript required for critical customer flows
- HTML forms for cart and checkout
- JSON-LD structured data on storefront/product pages

### Branding and media

- Shop branding is configurable via admin settings:
  - shop name
  - owner
  - logo URL/upload
- Product images are URL or uploaded assets
- Product image fallback uses branding logo with neutral presentation when product image is absent

## Coding Standards & Patterns we follow

### General

- Prefer explicit readable code over abstraction-heavy patterns.
- Keep dependencies minimal and justified.
- Preserve SSR/no-JS critical path behavior.
- Favor small, maintainable modules.

### Security and privacy

- Validate and sanitize all form inputs.
- Use CSRF protection on state-changing forms.
- Keep wallet credentials internal-only.
- Never expose wallet RPC publicly.
- Avoid collecting unnecessary user data.

### Storage and migrations

- Use migration entries in `common/migrations.py` for schema evolution.
- Maintain backward-safe startup behavior.
- Keep snapshot integrity in `order_items` for historical consistency.

### Testing expectations

- Use pytest for all tests.
- Keep default suite deterministic and local (wallet mocked by default).
- Validate critical flows end-to-end in app-level tests.
- Use optional smoke tests for deployed environments.

## Agent Behavior Rules specific to this project

1. Preserve project philosophy: privacy-first, simple stack, low operational complexity.
2. Keep webshop and admin as separate services; do not merge boundaries.
3. Avoid introducing JS-dependent critical flows.
4. Avoid adding external services unless clearly necessary.
5. Prefer SQLite-compatible solutions unless user explicitly requests migration.
6. Keep wallet integration behind internal abstraction (`common/wallet_rpc.py`).
7. Ensure any new feature includes docs and tests updates.
8. When changing deploy behavior, update both:
   - default production path (`docker-compose.yml`)
   - staging path (`docker-compose.staging.yml` + `.env.staging.example`)
9. Do not edit historical memory files in `.opencode/`; only add new dated snapshots when required by rules.
10. Always consult the file linked under **Current Memory** first before making planning assumptions.
