from __future__ import annotations

import sqlite3

from common.utils import utcnow_iso


def track_event(
    conn: sqlite3.Connection,
    event_type: str,
    product_id: int | None = None,
    order_id: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO analytics_events (event_type, product_id, order_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_type, product_id, order_id, utcnow_iso()),
    )
