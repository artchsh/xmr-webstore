# Testing Strategy (MVP v1)

## Phase 1: Testing architecture

The suite is intentionally split by risk area and execution cost.

- **unit tests**
  - pure utility/security helpers and wallet RPC parsing behavior.
  - fast, isolated, deterministic.
- **database tests**
  - migration sanity, constraints, foreign keys, snapshot integrity.
  - runs on isolated SQLite test DB.
- **service-layer tests**
  - order/payment reconciliation logic in `common/order_poller.py`.
  - mocks wallet transfers to test all state transitions.
- **webshop route/flow tests**
  - end-user SSR flows: browse -> cart -> checkout -> order -> download.
  - uses FastAPI `TestClient` with mocked wallet.
- **webshop SSR rendering tests**
  - verifies key HTML content/forms and non-JS critical paths.
- **admin route/flow tests**
  - login, auth guards, product CRUD, order visibility/actions, wallet page.
  - uses FastAPI `TestClient` with mocked wallet.
- **security/validation tests**
  - CSRF, auth checks, malformed session handling, escaping, token/signature checks.
- **integration tests (local)**
  - cross-service behavior (admin-created product visible in webshop) and route separation.
- **optional integration smoke tests**
  - opt-in environment tests against running Docker/Caddy endpoints.

## Phase 2: Test folder structure

```text
tests/
├── conftest.py
├── helpers.py
├── mocks/
│   └── fake_wallet.py
├── unit/
│   ├── test_security_and_utils.py
│   └── test_wallet_rpc.py
├── db/
│   └── test_schema_and_persistence.py
├── service/
│   └── test_order_poller.py
├── webshop/
│   ├── test_webshop_backend_flows.py
│   └── test_webshop_ssr_rendering.py
├── admin/
│   └── test_admin_backend_flows.py
├── security/
│   └── test_security_validation.py
└── integration/
    ├── test_service_separation.py
    └── test_optional_smoke.py
```

## Phase 3: Test infrastructure

- `pytest` + `pytest-asyncio` configured in `pytest.ini`.
- Isolated test DB and digital goods directory are provisioned per test via `tests/conftest.py`.
- Production DB is never touched (`DATABASE_PATH` forced to temp path).
- App fixtures reload webshop/admin modules with test env.
- Wallet RPC is mocked by default using `tests/mocks/fake_wallet.py`.
- Shared factories provide deterministic product/order fixtures.

## Phase 4-9: Coverage map

- **DB:** schema, migrations, constraints, snapshot behavior, cascade behavior, analytics insert.
- **Webshop backend:** homepage/product/cart/checkout/order/download flows, invalid inputs, token handling.
- **Webshop SSR:** HTML content/forms/totals/messages/download links/no required JS.
- **Admin backend:** login/auth, CSRF-protected CRUD, order views/actions, wallet + analytics views.
- **Wallet layer:** RPC error handling, wallet-open/create behavior, transfer parsing.
- **Payment lifecycle:** pending -> waiting confirmations -> completed / expired transitions.
- **Security:** CSRF enforcement, auth protection, traversal rejection, template escaping, signature checks.

## Phase 10: Optional integration smoke guidance

`tests/integration/test_optional_smoke.py` is skipped by default unless env vars are set.

- `SHOP_SMOKE_URL` (example: `https://shop.example.com`)
- `ADMIN_SMOKE_URL` (example: `http://127.0.0.1:8081`)

This keeps default local runs fast while allowing a minimal deployment smoke layer.

## What is mocked vs integration-tested

- **Mocked in default suite:** wallet-rpc network calls, remote Monero node behavior.
- **Real in default suite:**
  - FastAPI routing + middleware behavior
  - template rendering
  - SQLite schema + writes/reads
  - form submission + redirects + session cookies
  - business logic/state transitions
- **Optional real integration:** containerized deployment endpoints via smoke tests.

## Run commands

Install test dependencies:

```bash
pip install -r requirements-dev.txt
```

Run everything (default fast local suite):

```bash
pytest
```

Run by category:

```bash
pytest -m unit
pytest -m db
pytest -m webshop
pytest -m admin
pytest -m service
pytest -m security
pytest -m integration
```

Run optional smoke tests (against running services):

```bash
SHOP_SMOKE_URL=https://shop.example.com ADMIN_SMOKE_URL=http://127.0.0.1:8081 pytest -m optional_integration
```

Coverage example:

```bash
pytest --cov=common --cov=services --cov-report=term-missing
```
