from __future__ import annotations

import asyncio
import logging
import sqlite3

from common.analytics import track_event
from common.db import connect_db
from common.utils import parse_iso, utcnow, utcnow_iso
from common.wallet_rpc import MoneroWalletRPC, WalletRPCError


logger = logging.getLogger(__name__)


ORDER_PENDING_PAYMENT = "pending_payment"
ORDER_WAITING_CONFIRMATIONS = "waiting_confirmations"
ORDER_COMPLETED = "completed"
ORDER_EXPIRED = "expired"
ORDER_CANCELLED = "cancelled"

PAYMENT_PENDING = "pending"
PAYMENT_WAITING_CONFIRMATIONS = "waiting_confirmations"
PAYMENT_CONFIRMED = "confirmed"
PAYMENT_EXPIRED = "expired"


async def reconcile_orders_once(
    db_path: str,
    wallet: MoneroWalletRPC,
    required_confirmations: int,
) -> None:
    conn = connect_db(db_path)
    try:
        open_orders = conn.execute(
            """
            SELECT
                o.id AS order_id,
                o.status AS order_status,
                o.expires_at AS expires_at,
                o.total_atomic AS total_atomic,
                p.id AS payment_request_id,
                p.payment_subaddress_index AS subaddress_index,
                p.requested_atomic AS requested_atomic,
                p.received_atomic AS received_atomic
            FROM orders o
            JOIN payment_requests p ON p.order_id = o.id
            WHERE o.status IN (?, ?)
            ORDER BY o.created_at ASC
            """,
            (ORDER_PENDING_PAYMENT, ORDER_WAITING_CONFIRMATIONS),
        ).fetchall()

        now = utcnow()
        for row in open_orders:
            order_id = int(row["order_id"])
            order_status = str(row["order_status"])
            expires_at = parse_iso(str(row["expires_at"]))
            requested_atomic = int(row["requested_atomic"])
            payment_request_id = int(row["payment_request_id"])
            subaddress_index = int(row["subaddress_index"])

            transfers = await wallet.get_incoming_transfers(subaddress_index)

            total_received = sum(t.amount for t in transfers)
            confirmed_received = sum(
                t.amount for t in transfers if t.confirmations >= required_confirmations
            )
            max_confirmations = max((t.confirmations for t in transfers), default=0)
            confirmed_txid = ""
            for transfer in transfers:
                if transfer.confirmations >= required_confirmations:
                    confirmed_txid = transfer.txid
                    break

            if now > expires_at and total_received < requested_atomic:
                with conn:
                    conn.execute(
                        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                        (ORDER_EXPIRED, utcnow_iso(), order_id),
                    )
                    conn.execute(
                        """
                        UPDATE payment_requests
                        SET
                            status = ?,
                            received_atomic = ?,
                            confirmation_count = ?,
                            updated_at = ?,
                            last_checked_at = ?
                        WHERE id = ?
                        """,
                        (
                            PAYMENT_EXPIRED,
                            total_received,
                            max_confirmations,
                            utcnow_iso(),
                            utcnow_iso(),
                            payment_request_id,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO delivery_events (order_id, event_type, detail, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            order_id,
                            "order_expired",
                            "Order expired before payment",
                            utcnow_iso(),
                        ),
                    )
                continue

            new_order_status = order_status
            new_payment_status = PAYMENT_PENDING

            if confirmed_received >= requested_atomic:
                new_order_status = ORDER_COMPLETED
                new_payment_status = PAYMENT_CONFIRMED
            elif total_received >= requested_atomic:
                new_order_status = ORDER_WAITING_CONFIRMATIONS
                new_payment_status = PAYMENT_WAITING_CONFIRMATIONS
            elif total_received > 0:
                new_order_status = ORDER_PENDING_PAYMENT
                new_payment_status = PAYMENT_PENDING

            paid_at = utcnow_iso() if new_order_status == ORDER_COMPLETED else None

            with conn:
                conn.execute(
                    """
                    UPDATE payment_requests
                    SET
                        received_atomic = ?,
                        confirmation_count = ?,
                        txid = COALESCE(?, txid),
                        status = ?,
                        updated_at = ?,
                        last_checked_at = ?
                    WHERE id = ?
                    """,
                    (
                        total_received,
                        max_confirmations,
                        confirmed_txid or None,
                        new_payment_status,
                        utcnow_iso(),
                        utcnow_iso(),
                        payment_request_id,
                    ),
                )

                conn.execute(
                    """
                    UPDATE orders
                    SET
                        status = ?,
                        paid_atomic = ?,
                        confirmation_count = ?,
                        payment_txid = COALESCE(?, payment_txid),
                        paid_at = COALESCE(?, paid_at),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_order_status,
                        confirmed_received,
                        max_confirmations,
                        confirmed_txid or None,
                        paid_at,
                        utcnow_iso(),
                        order_id,
                    ),
                )

                if order_status not in {
                    ORDER_WAITING_CONFIRMATIONS,
                    ORDER_COMPLETED,
                } and new_order_status in {
                    ORDER_WAITING_CONFIRMATIONS,
                    ORDER_COMPLETED,
                }:
                    track_event(conn, "order_paid", order_id=order_id)

                if (
                    order_status != ORDER_COMPLETED
                    and new_order_status == ORDER_COMPLETED
                ):
                    track_event(conn, "order_completed", order_id=order_id)
                    conn.execute(
                        """
                        INSERT INTO delivery_events (order_id, event_type, detail, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            order_id,
                            "order_completed",
                            "Payment reached required confirmations",
                            utcnow_iso(),
                        ),
                    )
    finally:
        conn.close()


async def order_polling_loop(
    db_path: str,
    wallet: MoneroWalletRPC,
    required_confirmations: int,
    poll_interval_seconds: int,
) -> None:
    while True:
        try:
            await reconcile_orders_once(db_path, wallet, required_confirmations)
        except WalletRPCError as exc:
            logger.warning("Wallet RPC unavailable during poll: %s", exc)
        except Exception:
            logger.exception("Unhandled error in order polling loop")
        await asyncio.sleep(poll_interval_seconds)
