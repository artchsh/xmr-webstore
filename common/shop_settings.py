from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.utils import utcnow_iso


@dataclass(frozen=True)
class ShopBranding:
    name: str
    owner: str
    logo_url: str
    logo_path: str


def get_shop_branding(
    conn: sqlite3.Connection,
    default_name: str,
    default_owner: str,
    default_logo_url: str,
) -> ShopBranding:
    rows = conn.execute(
        """
        SELECT setting_key, setting_value
        FROM shop_settings
        WHERE setting_key IN ('shop_name', 'shop_owner', 'shop_logo_url', 'shop_logo_path')
        """
    ).fetchall()
    values = {str(row["setting_key"]): str(row["setting_value"] or "") for row in rows}
    return ShopBranding(
        name=values.get("shop_name", "") or default_name,
        owner=values.get("shop_owner", "") or default_owner,
        logo_url=values.get("shop_logo_url", "") or default_logo_url,
        logo_path=values.get("shop_logo_path", ""),
    )


def upsert_shop_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO shop_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (key, value, utcnow_iso()),
    )
