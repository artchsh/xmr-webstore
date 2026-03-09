from __future__ import annotations

import asyncio
import sqlite3

import pytest

import common.order_poller as order_poller
from common.wallet_rpc import IncomingTransfer, WalletRPCError


pytestmark = [pytest.mark.service]


class PollerWallet:
    def __init__(self, transfers_by_index: dict[int, list[IncomingTransfer]]) -> None:
        self.transfers_by_index = transfers_by_index

    async def get_incoming_transfers(
        self, subaddress_index: int
    ) -> list[IncomingTransfer]:
        return self.transfers_by_index.get(subaddress_index, [])


@pytest.mark.asyncio
async def test_reconcile_updates_waiting_confirmations(
    db_path: str,
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order(
        status="pending_payment",
        total_atomic=1_000,
        payment_received_atomic=0,
        payment_confirmations=0,
    )

    wallet = PollerWallet(
        {
            order["payment_subaddress_index"]: [
                IncomingTransfer(amount=1_000, confirmations=2, txid="tx-low-conf")
            ]
        }
    )

    await order_poller.reconcile_orders_once(db_path, wallet, required_confirmations=10)

    row = sqlite_conn.execute(
        "SELECT status, confirmation_count, paid_atomic FROM orders WHERE id = ?",
        (order["order_id"],),
    ).fetchone()
    payment = sqlite_conn.execute(
        "SELECT status, received_atomic, confirmation_count FROM payment_requests WHERE order_id = ?",
        (order["order_id"],),
    ).fetchone()

    assert row["status"] == "waiting_confirmations"
    assert int(row["paid_atomic"]) == 0
    assert payment["status"] == "waiting_confirmations"
    assert int(payment["received_atomic"]) == 1_000
    assert int(payment["confirmation_count"]) == 2


@pytest.mark.asyncio
async def test_reconcile_transitions_to_completed_and_tracks_events(
    db_path: str,
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order(status="pending_payment", total_atomic=4_000)

    wallet = PollerWallet(
        {
            order["payment_subaddress_index"]: [
                IncomingTransfer(amount=4_000, confirmations=15, txid="tx-complete")
            ]
        }
    )

    await order_poller.reconcile_orders_once(db_path, wallet, required_confirmations=10)

    row = sqlite_conn.execute(
        """
        SELECT status, paid_atomic, confirmation_count, payment_txid, paid_at
        FROM orders
        WHERE id = ?
        """,
        (order["order_id"],),
    ).fetchone()
    assert row["status"] == "completed"
    assert int(row["paid_atomic"]) == 4_000
    assert int(row["confirmation_count"]) == 15
    assert row["payment_txid"] == "tx-complete"
    assert row["paid_at"] is not None

    analytics_types = {
        item["event_type"]
        for item in sqlite_conn.execute(
            "SELECT event_type FROM analytics_events WHERE order_id = ?",
            (order["order_id"],),
        ).fetchall()
    }
    assert "order_paid" in analytics_types
    assert "order_completed" in analytics_types

    event = sqlite_conn.execute(
        "SELECT event_type FROM delivery_events WHERE order_id = ? ORDER BY id DESC LIMIT 1",
        (order["order_id"],),
    ).fetchone()
    assert event["event_type"] == "order_completed"


@pytest.mark.asyncio
async def test_reconcile_marks_expired_when_underpaid(
    db_path: str,
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order(
        status="pending_payment", total_atomic=1_500, expires_in_minutes=-5
    )

    wallet = PollerWallet(
        {
            order["payment_subaddress_index"]: [
                IncomingTransfer(amount=700, confirmations=20, txid="tx-partial")
            ]
        }
    )

    await order_poller.reconcile_orders_once(db_path, wallet, required_confirmations=10)

    status = sqlite_conn.execute(
        "SELECT status FROM orders WHERE id = ?", (order["order_id"],)
    ).fetchone()[0]
    payment = sqlite_conn.execute(
        "SELECT status, received_atomic FROM payment_requests WHERE order_id = ?",
        (order["order_id"],),
    ).fetchone()

    assert status == "expired"
    assert payment["status"] == "expired"
    assert int(payment["received_atomic"]) == 700


@pytest.mark.asyncio
async def test_reconcile_does_not_duplicate_completion_events(
    db_path: str,
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order(status="pending_payment", total_atomic=3_300)
    wallet = PollerWallet(
        {
            order["payment_subaddress_index"]: [
                IncomingTransfer(amount=3_300, confirmations=12, txid="tx-dup-safe")
            ]
        }
    )

    await order_poller.reconcile_orders_once(db_path, wallet, required_confirmations=10)
    await order_poller.reconcile_orders_once(db_path, wallet, required_confirmations=10)

    completed_count = sqlite_conn.execute(
        """
        SELECT COUNT(*)
        FROM analytics_events
        WHERE order_id = ? AND event_type = 'order_completed'
        """,
        (order["order_id"],),
    ).fetchone()[0]

    assert completed_count == 1


@pytest.mark.asyncio
async def test_polling_loop_catches_wallet_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    async def fake_reconcile(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise WalletRPCError("wallet down")
        raise asyncio.CancelledError()

    async def fake_sleep(_seconds: int):
        return None

    monkeypatch.setattr(order_poller, "reconcile_orders_once", fake_reconcile)
    monkeypatch.setattr(order_poller.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await order_poller.order_polling_loop(
            db_path="/tmp/unused.db",
            wallet=PollerWallet({}),
            required_confirmations=10,
            poll_interval_seconds=1,
        )

    assert calls["count"] == 2
