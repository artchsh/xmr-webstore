from __future__ import annotations

import os
from dataclasses import dataclass


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass(frozen=True)
class AppSettings:
    app_env: str
    db_path: str
    digital_goods_dir: str
    product_images_dir: str
    cookie_secure: bool
    public_base_url: str
    session_secret: str
    download_token_secret: str
    order_expiry_minutes: int
    required_confirmations: int
    payment_poll_interval_seconds: int
    wallet_rpc_url: str
    wallet_rpc_username: str
    wallet_rpc_password: str
    wallet_file: str
    wallet_password: str
    wallet_auto_create: bool
    wallet_create_language: str
    monero_remote_nodes: list[str]


@dataclass(frozen=True)
class AdminSettings:
    app_env: str
    db_path: str
    digital_goods_dir: str
    product_images_dir: str
    cookie_secure: bool
    session_secret: str
    wallet_rpc_url: str
    wallet_rpc_username: str
    wallet_rpc_password: str
    wallet_file: str
    wallet_password: str
    wallet_auto_create: bool
    wallet_create_language: str
    monero_remote_nodes: list[str]
    admin_username: str
    admin_password: str
    admin_password_hash: str


def load_webshop_settings() -> AppSettings:
    primary_node = os.getenv("MONERO_REMOTE_NODE", "")
    nodes = _to_list(os.getenv("MONERO_REMOTE_NODES"))
    if primary_node and primary_node not in nodes:
        nodes.insert(0, primary_node)

    return AppSettings(
        app_env=os.getenv("APP_ENV", "development"),
        db_path=os.getenv("DATABASE_PATH", "/data/webshop.db"),
        digital_goods_dir=os.getenv("DIGITAL_GOODS_DIR", "/data/digital_goods"),
        product_images_dir=os.getenv("PRODUCT_IMAGES_DIR", "/data/product_images"),
        cookie_secure=_to_bool(os.getenv("COOKIE_SECURE"), default=False),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost"),
        session_secret=os.getenv("WEB_SESSION_SECRET", "change-me-web-session-secret"),
        download_token_secret=os.getenv(
            "DOWNLOAD_TOKEN_SECRET", "change-me-download-secret"
        ),
        order_expiry_minutes=_to_int(os.getenv("ORDER_EXPIRY_MINUTES"), 1440),
        required_confirmations=_to_int(os.getenv("REQUIRED_CONFIRMATIONS"), 10),
        payment_poll_interval_seconds=_to_int(
            os.getenv("PAYMENT_POLL_INTERVAL_SECONDS"), 30
        ),
        wallet_rpc_url=os.getenv("WALLET_RPC_URL", "http://wallet-rpc:18083/json_rpc"),
        wallet_rpc_username=os.getenv("WALLET_RPC_USERNAME", "walletrpc"),
        wallet_rpc_password=os.getenv(
            "WALLET_RPC_PASSWORD", "change-me-wallet-rpc-password"
        ),
        wallet_file=os.getenv("WALLET_FILE", "store.wallet"),
        wallet_password=os.getenv("WALLET_PASSWORD", ""),
        wallet_auto_create=_to_bool(os.getenv("WALLET_AUTO_CREATE"), default=False),
        wallet_create_language=os.getenv("WALLET_CREATE_LANGUAGE", "English"),
        monero_remote_nodes=nodes,
    )


def load_admin_settings() -> AdminSettings:
    primary_node = os.getenv("MONERO_REMOTE_NODE", "")
    nodes = _to_list(os.getenv("MONERO_REMOTE_NODES"))
    if primary_node and primary_node not in nodes:
        nodes.insert(0, primary_node)

    return AdminSettings(
        app_env=os.getenv("APP_ENV", "development"),
        db_path=os.getenv("DATABASE_PATH", "/data/webshop.db"),
        digital_goods_dir=os.getenv("DIGITAL_GOODS_DIR", "/data/digital_goods"),
        product_images_dir=os.getenv("PRODUCT_IMAGES_DIR", "/data/product_images"),
        cookie_secure=_to_bool(os.getenv("COOKIE_SECURE"), default=False),
        session_secret=os.getenv(
            "ADMIN_SESSION_SECRET", "change-me-admin-session-secret"
        ),
        wallet_rpc_url=os.getenv("WALLET_RPC_URL", "http://wallet-rpc:18083/json_rpc"),
        wallet_rpc_username=os.getenv("WALLET_RPC_USERNAME", "walletrpc"),
        wallet_rpc_password=os.getenv(
            "WALLET_RPC_PASSWORD", "change-me-wallet-rpc-password"
        ),
        wallet_file=os.getenv("WALLET_FILE", "store.wallet"),
        wallet_password=os.getenv("WALLET_PASSWORD", ""),
        wallet_auto_create=_to_bool(os.getenv("WALLET_AUTO_CREATE"), default=False),
        wallet_create_language=os.getenv("WALLET_CREATE_LANGUAGE", "English"),
        monero_remote_nodes=nodes,
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
        admin_password_hash=os.getenv("ADMIN_PASSWORD_HASH", ""),
    )
