from __future__ import annotations

import os

import httpx
import pytest


pytestmark = [pytest.mark.optional_integration]


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"{name} not set; skipping optional integration smoke test")
    return value


def test_optional_caddy_shop_health_smoke() -> None:
    base_url = _require_env("SHOP_SMOKE_URL")
    response = httpx.get(
        f"{base_url.rstrip('/')}/health", timeout=10.0, follow_redirects=True
    )
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_optional_admin_health_smoke() -> None:
    base_url = _require_env("ADMIN_SMOKE_URL")
    response = httpx.get(
        f"{base_url.rstrip('/')}/health", timeout=10.0, follow_redirects=True
    )
    assert response.status_code == 200
    assert response.json().get("status") == "ok"
