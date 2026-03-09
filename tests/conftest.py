from __future__ import annotations

import asyncio
import importlib
import os
import sqlite3
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from common.db import connect_db
from common.migrations import run_migrations
from common.utils import utcnow, utcnow_iso
from tests.helpers import extract_csrf_token
from tests.mocks.fake_wallet import FakeWalletRPC


def _reload_module(module_name: str):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


@pytest.fixture(autouse=True)
def reset_fake_wallet_instances() -> None:
    FakeWalletRPC.instances.clear()


@pytest.fixture
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    db_path = tmp_path / "test-webshop.db"
    goods_dir = tmp_path / "digital_goods"
    images_dir = tmp_path / "product_images"
    branding_dir = tmp_path / "branding"
    goods_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    branding_dir.mkdir(parents=True, exist_ok=True)

    env = {
        "APP_ENV": "test",
        "DATABASE_PATH": str(db_path),
        "DIGITAL_GOODS_DIR": str(goods_dir),
        "PRODUCT_IMAGES_DIR": str(images_dir),
        "BRANDING_ASSETS_DIR": str(branding_dir),
        "COOKIE_SECURE": "false",
        "PUBLIC_BASE_URL": "http://testserver",
        "ALLOW_EXTERNAL_ASSET_URLS": "true",
        "MAX_UPLOAD_BYTES": "1048576",
        "WEB_SESSION_SECRET": "test-web-session-secret",
        "ADMIN_SESSION_SECRET": "test-admin-session-secret",
        "DOWNLOAD_TOKEN_SECRET": "test-download-secret",
        "ORDER_EXPIRY_MINUTES": "60",
        "REQUIRED_CONFIRMATIONS": "10",
        "PAYMENT_POLL_INTERVAL_SECONDS": "3600",
        "WALLET_RPC_URL": "http://wallet-rpc:18083/json_rpc",
        "WALLET_RPC_USERNAME": "test-wallet",
        "WALLET_RPC_PASSWORD": "test-wallet-password",
        "WALLET_FILE": "test.wallet",
        "WALLET_PASSWORD": "test-wallet-file-password",
        "WALLET_AUTO_CREATE": "true",
        "WALLET_CREATE_LANGUAGE": "English",
        "MONERO_REMOTE_NODE": "node1.example:18089",
        "MONERO_REMOTE_NODES": "node1.example:18089,node2.example:18089",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin-password",
        "ADMIN_PASSWORD_HASH": "",
    }

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    return {
        "db_path": db_path,
        "digital_goods_dir": goods_dir,
        "product_images_dir": images_dir,
        "branding_assets_dir": branding_dir,
        "admin_username": env["ADMIN_USERNAME"],
        "admin_password": env["ADMIN_PASSWORD"],
        "download_token_secret": env["DOWNLOAD_TOKEN_SECRET"],
    }


@pytest.fixture
def sqlite_conn(app_env: dict[str, Any]) -> sqlite3.Connection:
    conn = connect_db(str(app_env["db_path"]))
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def make_digital_good(app_env: dict[str, Any]):
    def _make(
        filename: str = "sample.txt", content: str | bytes = "sample payload"
    ) -> Path:
        path = Path(app_env["digital_goods_dir"]) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    return _make


@pytest.fixture
def create_product(
    sqlite_conn: sqlite3.Connection,
    make_digital_good,
):
    counter = {"n": 0}

    def _create(
        *,
        slug: str | None = None,
        title: str | None = None,
        short_description: str = "short",
        long_description: str = "long",
        price_atomic: int = 1_000_000_000_000,
        file_path: str | None = None,
        is_active: int = 1,
        is_archived: int = 0,
    ) -> int:
        counter["n"] += 1
        idx = counter["n"]
        slug = slug or f"test-product-{idx}"
        title = title or f"Test Product {idx}"

        if file_path is None:
            path = make_digital_good(
                filename=f"product-{idx}.txt", content=f"payload-{idx}"
            )
            file_path = path.name

        now_iso = utcnow_iso()
        with sqlite_conn:
            cursor = sqlite_conn.execute(
                """
                INSERT INTO products (
                    slug,
                    title,
                    short_description,
                    long_description,
                    price_atomic,
                    delivery_type,
                    file_path,
                    is_active,
                    is_archived,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, 'file', ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    title,
                    short_description,
                    long_description,
                    price_atomic,
                    file_path,
                    is_active,
                    is_archived,
                    now_iso,
                    now_iso,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to insert product")
            return int(cursor.lastrowid)

    return _create


@pytest.fixture
def create_order(
    sqlite_conn: sqlite3.Connection,
    create_product,
):
    def _create(
        *,
        product_id: int | None = None,
        status: str = "pending_payment",
        payment_status: str | None = None,
        total_atomic: int | None = None,
        paid_atomic: int = 0,
        confirmation_count: int = 0,
        payment_confirmations: int = 0,
        payment_received_atomic: int = 0,
        expires_in_minutes: int = 60,
        token: str | None = None,
    ) -> dict[str, Any]:
        if product_id is None:
            product_id = create_product()

        product = sqlite_conn.execute(
            "SELECT id, slug, title, price_atomic, file_path FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not product:
            raise AssertionError("Product missing for order fixture")

        requested = int(
            total_atomic if total_atomic is not None else product["price_atomic"]
        )

        if payment_status is None:
            payment_status = {
                "pending_payment": "pending",
                "waiting_confirmations": "waiting_confirmations",
                "completed": "confirmed",
                "expired": "expired",
                "cancelled": "pending",
            }[status]

        now = utcnow()
        expires_at = now + timedelta(minutes=expires_in_minutes)
        if status == "expired":
            expires_at = now - timedelta(minutes=5)

        token = token or uuid.uuid4().hex
        payment_subaddress = f"84FixtureAddress{uuid.uuid4().hex[:12]}"
        payment_index = int(uuid.uuid4().int % 10_000)
        created_at = utcnow_iso()

        if status == "completed" and paid_atomic == 0:
            paid_atomic = requested
        if status == "completed" and payment_received_atomic == 0:
            payment_received_atomic = requested

        with sqlite_conn:
            order_cursor = sqlite_conn.execute(
                """
                INSERT INTO orders (
                    public_token,
                    session_token,
                    status,
                    total_atomic,
                    payment_subaddress,
                    payment_subaddress_index,
                    payment_txid,
                    paid_atomic,
                    confirmation_count,
                    created_at,
                    updated_at,
                    paid_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    "session-fixture",
                    status,
                    requested,
                    payment_subaddress,
                    payment_index,
                    "tx-fixture" if status == "completed" else None,
                    paid_atomic,
                    confirmation_count,
                    created_at,
                    created_at,
                    created_at if status == "completed" else None,
                    expires_at.replace(microsecond=0).isoformat(),
                ),
            )
            if order_cursor.lastrowid is None:
                raise RuntimeError("Failed to create order fixture")
            order_id = int(order_cursor.lastrowid)

            item_cursor = sqlite_conn.execute(
                """
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    product_slug,
                    product_title,
                    unit_price_atomic,
                    quantity,
                    delivery_type,
                    delivery_ref,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'file', ?, ?)
                """,
                (
                    order_id,
                    int(product["id"]),
                    str(product["slug"]),
                    str(product["title"]),
                    int(product["price_atomic"]),
                    1,
                    str(product["file_path"]),
                    created_at,
                ),
            )
            if item_cursor.lastrowid is None:
                raise RuntimeError("Failed to create order item fixture")
            item_id = int(item_cursor.lastrowid)

            sqlite_conn.execute(
                """
                INSERT INTO payment_requests (
                    order_id,
                    payment_subaddress,
                    payment_subaddress_index,
                    requested_atomic,
                    received_atomic,
                    confirmation_count,
                    txid,
                    status,
                    created_at,
                    updated_at,
                    last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    payment_subaddress,
                    payment_index,
                    requested,
                    payment_received_atomic,
                    payment_confirmations,
                    "tx-fixture" if status == "completed" else None,
                    payment_status,
                    created_at,
                    created_at,
                    created_at,
                ),
            )

        return {
            "order_id": order_id,
            "item_id": item_id,
            "token": token,
            "product_id": int(product["id"]),
            "payment_subaddress": payment_subaddress,
            "payment_subaddress_index": payment_index,
            "requested_atomic": requested,
        }

    return _create


@pytest.fixture
def webshop_app(app_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
    import common.order_poller as order_poller
    import common.wallet_rpc as wallet_rpc

    async def _idle_order_poller(*_args, **_kwargs) -> None:
        while True:
            await asyncio.sleep(3600)

    monkeypatch.setattr(wallet_rpc, "MoneroWalletRPC", FakeWalletRPC)
    monkeypatch.setattr(order_poller, "order_polling_loop", _idle_order_poller)

    module = _reload_module("services.webshop.main")
    return module.app


@pytest.fixture
def webshop_client(webshop_app):
    with TestClient(webshop_app) as client:
        yield client


@pytest.fixture
def webshop_wallet(webshop_client):
    return webshop_client.app.state.wallet


@pytest.fixture
def admin_app(app_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
    import common.wallet_rpc as wallet_rpc

    monkeypatch.setattr(wallet_rpc, "MoneroWalletRPC", FakeWalletRPC)
    module = _reload_module("services.admin.main")
    return module.app


@pytest.fixture
def admin_client(admin_app):
    with TestClient(admin_app) as client:
        yield client


@pytest.fixture
def admin_wallet(admin_client):
    return admin_client.app.state.wallet


@pytest.fixture
def admin_client_logged_in(admin_client, app_env: dict[str, Any]):
    login_page = admin_client.get("/login")
    assert login_page.status_code == 200
    csrf = extract_csrf_token(login_page.text)

    response = admin_client.post(
        "/login",
        data={
            "username": app_env["admin_username"],
            "password": app_env["admin_password"],
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    return admin_client


@pytest.fixture
def db_path(app_env: dict[str, Any]) -> str:
    return os.fspath(app_env["db_path"])
