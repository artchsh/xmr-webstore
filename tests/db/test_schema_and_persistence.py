from __future__ import annotations

import sqlite3

import pytest

from common.analytics import track_event
from common.migrations import MIGRATIONS, run_migrations
from common.utils import utcnow_iso


pytestmark = [pytest.mark.db]


def test_run_migrations_creates_schema(sqlite_conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    expected = {
        "products",
        "orders",
        "order_items",
        "payment_requests",
        "delivery_events",
        "analytics_events",
        "admin_users",
    }
    assert expected.issubset(tables)

    user_version = sqlite_conn.execute("PRAGMA user_version").fetchone()[0]
    assert user_version == len(MIGRATIONS)


def test_migrations_are_idempotent(sqlite_conn: sqlite3.Connection) -> None:
    before = sqlite_conn.execute("PRAGMA user_version").fetchone()[0]
    run_migrations(sqlite_conn)
    after = sqlite_conn.execute("PRAGMA user_version").fetchone()[0]
    assert before == after == len(MIGRATIONS)


def test_product_slug_unique_constraint(
    sqlite_conn: sqlite3.Connection,
    create_product,
) -> None:
    create_product(slug="unique-slug")
    with pytest.raises(sqlite3.IntegrityError):
        create_product(slug="unique-slug")


def test_payment_request_is_unique_per_order(
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order()
    with pytest.raises(sqlite3.IntegrityError):
        with sqlite_conn:
            sqlite_conn.execute(
                """
                INSERT INTO payment_requests (
                    order_id,
                    payment_subaddress,
                    payment_subaddress_index,
                    requested_atomic,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["order_id"],
                    "84DuplicateAddress",
                    99,
                    order["requested_atomic"],
                    "pending",
                    utcnow_iso(),
                    utcnow_iso(),
                ),
            )


def test_order_items_snapshot_survives_product_changes(
    sqlite_conn: sqlite3.Connection,
    create_product,
    create_order,
) -> None:
    product_id = create_product(
        slug="snapshot-product",
        title="Original Title",
        price_atomic=2_000_000_000_000,
    )
    order = create_order(product_id=product_id)

    with sqlite_conn:
        sqlite_conn.execute(
            """
            UPDATE products
            SET title = ?, price_atomic = ?, updated_at = ?
            WHERE id = ?
            """,
            ("Changed Title", 9_000_000_000_000, utcnow_iso(), product_id),
        )

    item = sqlite_conn.execute(
        "SELECT product_title, unit_price_atomic FROM order_items WHERE order_id = ?",
        (order["order_id"],),
    ).fetchone()

    assert item["product_title"] == "Original Title"
    assert int(item["unit_price_atomic"]) == 2_000_000_000_000


def test_order_delete_cascades_to_child_rows(
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order(status="pending_payment")
    with sqlite_conn:
        sqlite_conn.execute(
            """
            INSERT INTO delivery_events (order_id, event_type, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (order["order_id"], "test_event", "fixture", utcnow_iso()),
        )
        sqlite_conn.execute("DELETE FROM orders WHERE id = ?", (order["order_id"],))

    assert (
        sqlite_conn.execute(
            "SELECT COUNT(*) FROM order_items WHERE order_id = ?", (order["order_id"],)
        ).fetchone()[0]
        == 0
    )
    assert (
        sqlite_conn.execute(
            "SELECT COUNT(*) FROM payment_requests WHERE order_id = ?",
            (order["order_id"],),
        ).fetchone()[0]
        == 0
    )
    assert (
        sqlite_conn.execute(
            "SELECT COUNT(*) FROM delivery_events WHERE order_id = ?",
            (order["order_id"],),
        ).fetchone()[0]
        == 0
    )


def test_analytics_event_insert(
    sqlite_conn: sqlite3.Connection,
    create_product,
    create_order,
) -> None:
    product_id = create_product()
    order = create_order(product_id=product_id)
    with sqlite_conn:
        track_event(
            sqlite_conn,
            event_type="order_created",
            product_id=product_id,
            order_id=order["order_id"],
        )

    row = sqlite_conn.execute(
        "SELECT event_type, product_id, order_id FROM analytics_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["event_type"] == "order_created"
    assert int(row["product_id"]) == product_id
    assert int(row["order_id"]) == order["order_id"]
