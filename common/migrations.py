from __future__ import annotations

import sqlite3


MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        short_description TEXT NOT NULL,
        long_description TEXT NOT NULL,
        price_atomic INTEGER NOT NULL,
        delivery_type TEXT NOT NULL DEFAULT 'file',
        file_path TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        public_token TEXT NOT NULL UNIQUE,
        session_token TEXT,
        status TEXT NOT NULL,
        total_atomic INTEGER NOT NULL,
        payment_subaddress TEXT,
        payment_subaddress_index INTEGER,
        payment_txid TEXT,
        paid_atomic INTEGER NOT NULL DEFAULT 0,
        confirmation_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        paid_at TEXT,
        expires_at TEXT NOT NULL,
        cancelled_at TEXT
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER,
        product_slug TEXT NOT NULL,
        product_title TEXT NOT NULL,
        unit_price_atomic INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        delivery_type TEXT NOT NULL,
        delivery_ref TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL UNIQUE,
        payment_subaddress TEXT NOT NULL,
        payment_subaddress_index INTEGER NOT NULL,
        requested_atomic INTEGER NOT NULL,
        received_atomic INTEGER NOT NULL DEFAULT 0,
        confirmation_count INTEGER NOT NULL DEFAULT 0,
        txid TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_checked_at TEXT,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS delivery_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS analytics_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        product_id INTEGER,
        order_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_products_active_archived ON products(is_active, is_archived);
    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
    CREATE INDEX IF NOT EXISTS idx_orders_token ON orders(public_token);
    CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
    CREATE INDEX IF NOT EXISTS idx_payment_requests_order_id ON payment_requests(order_id);
    CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics_events(event_type);
    CREATE INDEX IF NOT EXISTS idx_analytics_created_at ON analytics_events(created_at);
    """,
    """
    ALTER TABLE products ADD COLUMN image_url TEXT;
    ALTER TABLE products ADD COLUMN image_path TEXT;
    """,
    """
    CREATE TABLE IF NOT EXISTS shop_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT NOT NULL UNIQUE,
        setting_value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]


def run_migrations(conn: sqlite3.Connection) -> None:
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    target_version = len(MIGRATIONS)

    if current_version >= target_version:
        return

    for idx, statement in enumerate(
        MIGRATIONS[current_version:], start=current_version + 1
    ):
        with conn:
            conn.executescript(statement)
            conn.execute(f"PRAGMA user_version = {idx}")
