from __future__ import annotations

import asyncio
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from common.analytics import track_event
from common.config import AppSettings, load_webshop_settings
from common.db import connect_db
from common.migrations import run_migrations
from common.order_poller import order_polling_loop
from common.security import (
    ensure_csrf_token,
    generate_download_signature,
    validate_csrf,
    verify_download_signature,
)
from common.utils import (
    atomic_to_xmr,
    random_token,
    utcnow,
    utcnow_iso,
    validate_relative_file,
)
from common.wallet_rpc import MoneroWalletRPC, WalletRPCError


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

settings: AppSettings = load_webshop_settings()
app = FastAPI(title="xmr-webshop")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="shop_session",
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["format_xmr"] = atomic_to_xmr


def db_conn() -> sqlite3.Connection:
    return connect_db(settings.db_path)


def get_cart(request: Request) -> dict[str, int]:
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        return {}
    clean: dict[str, int] = {}
    for key, value in cart.items():
        try:
            qty = int(value)
        except Exception:
            continue
        if qty > 0:
            clean[str(key)] = qty
    return clean


def save_cart(request: Request, cart: dict[str, int]) -> None:
    request.session["cart"] = cart


def cart_count(cart: dict[str, int]) -> int:
    return sum(cart.values())


def load_cart_items(
    conn: sqlite3.Connection, cart: dict[str, int]
) -> tuple[list[dict], int]:
    if not cart:
        return [], 0
    ids = []
    for key in cart.keys():
        try:
            ids.append(int(key))
        except ValueError:
            continue
    if not ids:
        return [], 0

    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT id, slug, title, short_description, long_description, price_atomic, file_path
        FROM products
        WHERE id IN ({placeholders}) AND is_active = 1 AND is_archived = 0
        """,
        ids,
    ).fetchall()

    by_id = {int(r["id"]): r for r in rows}
    items: list[dict] = []
    total = 0
    for key, qty in cart.items():
        try:
            product_id = int(key)
        except ValueError:
            continue
        row = by_id.get(product_id)
        if not row:
            continue
        unit = int(row["price_atomic"])
        line_total = unit * qty
        total += line_total
        items.append(
            {
                "product_id": product_id,
                "slug": row["slug"],
                "title": row["title"],
                "quantity": qty,
                "unit_price_atomic": unit,
                "line_total_atomic": line_total,
                "delivery_ref": row["file_path"],
            }
        )
    return items, total


def template_context(request: Request, **extra: object) -> dict[str, object]:
    cart = get_cart(request)
    context: dict[str, object] = {
        "request": request,
        "csrf_token": ensure_csrf_token(request.session),
        "cart_count": cart_count(cart),
    }
    context.update(extra)
    return context


@app.on_event("startup")
async def startup() -> None:
    Path(settings.digital_goods_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = db_conn()
    try:
        run_migrations(conn)
    finally:
        conn.close()

    wallet = MoneroWalletRPC(
        rpc_url=settings.wallet_rpc_url,
        username=settings.wallet_rpc_username,
        password=settings.wallet_rpc_password,
        wallet_file=settings.wallet_file,
        wallet_password=settings.wallet_password,
        wallet_auto_create=settings.wallet_auto_create,
        wallet_create_language=settings.wallet_create_language,
    )
    app.state.wallet = wallet
    app.state.poller_task = asyncio.create_task(
        order_polling_loop(
            db_path=settings.db_path,
            wallet=wallet,
            required_confirmations=settings.required_confirmations,
            poll_interval_seconds=settings.payment_poll_interval_seconds,
        )
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "poller_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    wallet = getattr(app.state, "wallet", None)
    if wallet is not None:
        await wallet.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def index(request: Request):
    conn = db_conn()
    try:
        products = conn.execute(
            """
            SELECT id, slug, title, short_description, price_atomic
            FROM products
            WHERE is_active = 1 AND is_archived = 0
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "index.html",
        template_context(request, products=products),
    )


@app.get("/product/{slug}")
async def product_detail(request: Request, slug: str):
    conn = db_conn()
    try:
        product = conn.execute(
            """
            SELECT id, slug, title, short_description, long_description, price_atomic
            FROM products
            WHERE slug = ? AND is_active = 1 AND is_archived = 0
            """,
            (slug,),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        with conn:
            track_event(conn, "product_page_view", product_id=int(product["id"]))
    finally:
        conn.close()

    return templates.TemplateResponse(
        "product_detail.html",
        template_context(request, product=product),
    )


@app.get("/cart")
async def view_cart(request: Request):
    conn = db_conn()
    try:
        items, total_atomic = load_cart_items(conn, get_cart(request))
    finally:
        conn.close()
    return templates.TemplateResponse(
        "cart.html",
        template_context(request, items=items, total_atomic=total_atomic),
    )


@app.post("/cart/add")
async def add_to_cart(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(1),
    csrf_token: str = Form(...),
):
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")
    if quantity < 1:
        quantity = 1

    conn = db_conn()
    try:
        product = conn.execute(
            "SELECT id FROM products WHERE id = ? AND is_active = 1 AND is_archived = 0",
            (product_id,),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        cart = get_cart(request)
        key = str(product_id)
        cart[key] = cart.get(key, 0) + quantity
        save_cart(request, cart)

        with conn:
            track_event(conn, "add_to_cart", product_id=product_id)
    finally:
        conn.close()

    return RedirectResponse(url="/cart", status_code=303)


@app.post("/cart/update")
async def update_cart(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    cart = get_cart(request)
    key = str(product_id)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    save_cart(request, cart)
    return RedirectResponse(url="/cart", status_code=303)


@app.post("/cart/clear")
async def clear_cart(request: Request, csrf_token: str = Form(...)):
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")
    save_cart(request, {})
    return RedirectResponse(url="/cart", status_code=303)


@app.get("/checkout")
async def checkout_get(request: Request):
    conn = db_conn()
    try:
        items, total_atomic = load_cart_items(conn, get_cart(request))
        if items:
            with conn:
                track_event(conn, "checkout_started")
    finally:
        conn.close()

    if not items:
        return RedirectResponse(url="/cart", status_code=303)

    return templates.TemplateResponse(
        "checkout.html",
        template_context(request, items=items, total_atomic=total_atomic),
    )


@app.post("/checkout")
async def checkout_post(request: Request, csrf_token: str = Form(...)):
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    conn = db_conn()
    try:
        cart = get_cart(request)
        items, total_atomic = load_cart_items(conn, cart)
        if not items:
            return RedirectResponse(url="/cart", status_code=303)

        order_token = random_token(24)
        session_token = request.session.get("session_ref")
        if not session_token:
            session_token = random_token(12)
            request.session["session_ref"] = session_token

        wallet: MoneroWalletRPC = app.state.wallet
        try:
            subaddr = await wallet.create_subaddress(f"order-{order_token[:12]}")
        except WalletRPCError:
            raise HTTPException(status_code=503, detail="Wallet service unavailable")

        payment_address = str(subaddr["address"])
        payment_index = int(subaddr["address_index"])
        now_iso = utcnow_iso()
        expires_iso = utcnow().replace(microsecond=0) + timedelta(
            minutes=settings.order_expiry_minutes
        )

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (
                    public_token,
                    session_token,
                    status,
                    total_atomic,
                    payment_subaddress,
                    payment_subaddress_index,
                    created_at,
                    updated_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_token,
                    session_token,
                    "pending_payment",
                    total_atomic,
                    payment_address,
                    payment_index,
                    now_iso,
                    now_iso,
                    expires_iso.isoformat(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create order")
            order_id = int(cursor.lastrowid)

            for item in items:
                conn.execute(
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item["product_id"],
                        item["slug"],
                        item["title"],
                        item["unit_price_atomic"],
                        item["quantity"],
                        "file",
                        item["delivery_ref"],
                        now_iso,
                    ),
                )

            conn.execute(
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
                    order_id,
                    payment_address,
                    payment_index,
                    total_atomic,
                    "pending",
                    now_iso,
                    now_iso,
                ),
            )

            track_event(conn, "order_created", order_id=order_id)

        save_cart(request, {})
    finally:
        conn.close()

    return RedirectResponse(url=f"/order/{order_token}", status_code=303)


@app.get("/order/{order_token}")
async def order_detail(request: Request, order_token: str):
    conn = db_conn()
    try:
        order = conn.execute(
            """
            SELECT
                o.id,
                o.public_token,
                o.status,
                o.total_atomic,
                o.confirmation_count,
                o.created_at,
                o.updated_at,
                o.paid_at,
                o.expires_at,
                p.payment_subaddress,
                p.requested_atomic,
                p.received_atomic,
                p.confirmation_count AS payment_confirmations,
                p.status AS payment_status
            FROM orders o
            JOIN payment_requests p ON p.order_id = o.id
            WHERE o.public_token = ?
            """,
            (order_token,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = conn.execute(
            """
            SELECT id, product_title, unit_price_atomic, quantity, delivery_ref
            FROM order_items
            WHERE order_id = ?
            ORDER BY id ASC
            """,
            (int(order["id"]),),
        ).fetchall()

        download_links: dict[int, dict[str, str | int]] = {}
        if order["status"] == "completed":
            expires = int(time.time()) + 600
            for item in items:
                item_id = int(item["id"])
                signature = generate_download_signature(
                    settings.download_token_secret,
                    order_token,
                    item_id,
                    expires,
                )
                download_links[item_id] = {"signature": signature, "expires": expires}
    finally:
        conn.close()

    return templates.TemplateResponse(
        "order.html",
        template_context(
            request,
            order=order,
            items=items,
            required_confirmations=settings.required_confirmations,
            download_links=download_links,
        ),
    )


@app.get("/order/{order_token}/receipt.txt")
async def order_receipt_text(order_token: str):
    conn = db_conn()
    try:
        order = conn.execute(
            """
            SELECT public_token, status, total_atomic, created_at, paid_at, expires_at
            FROM orders
            WHERE public_token = ?
            """,
            (order_token,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = conn.execute(
            """
            SELECT product_title, unit_price_atomic, quantity
            FROM order_items
            WHERE order_id = (SELECT id FROM orders WHERE public_token = ?)
            ORDER BY id ASC
            """,
            (order_token,),
        ).fetchall()
    finally:
        conn.close()

    lines = [
        "xmr-webshop receipt",
        f"order_token: {order['public_token']}",
        f"status: {order['status']}",
        f"total_xmr: {atomic_to_xmr(int(order['total_atomic']))}",
        f"created_at: {order['created_at']}",
        f"paid_at: {order['paid_at'] or '-'}",
        f"expires_at: {order['expires_at']}",
        "items:",
    ]
    for item in items:
        lines.append(
            f"- {item['product_title']} x {item['quantity']} @ {atomic_to_xmr(int(item['unit_price_atomic']))} XMR"
        )

    body = "\n".join(lines) + "\n"
    headers = {
        "Content-Disposition": f"attachment; filename=receipt-{order_token[:12]}.txt"
    }
    return PlainTextResponse(content=body, headers=headers)


@app.get("/order/{order_token}/download/{item_id}")
async def download_item(order_token: str, item_id: int, exp: int, sig: str):
    if not verify_download_signature(
        settings.download_token_secret, order_token, item_id, exp, sig
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired download token")

    conn = db_conn()
    try:
        row = conn.execute(
            """
            SELECT o.id AS order_id, o.status AS order_status, i.product_title, i.delivery_ref
            FROM orders o
            JOIN order_items i ON i.order_id = o.id
            WHERE o.public_token = ? AND i.id = ?
            """,
            (order_token, item_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        if row["order_status"] != "completed":
            raise HTTPException(status_code=403, detail="Order is not paid")

        try:
            relative_path = validate_relative_file(
                settings.digital_goods_dir, str(row["delivery_ref"])
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="File not available")

        with conn:
            track_event(conn, "download_accessed", order_id=int(row["order_id"]))
            conn.execute(
                """
                INSERT INTO delivery_events (order_id, event_type, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    int(row["order_id"]),
                    "download_accessed",
                    f"item_id={item_id}",
                    utcnow_iso(),
                ),
            )
    finally:
        conn.close()

    full_path = str((Path(settings.digital_goods_dir) / relative_path).resolve())
    filename = Path(relative_path).name
    return FileResponse(
        path=full_path, filename=filename, media_type="application/octet-stream"
    )
