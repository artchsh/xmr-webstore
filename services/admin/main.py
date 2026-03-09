from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from common.config import AdminSettings, load_admin_settings
from common.db import connect_db
from common.migrations import run_migrations
from common.security import (
    ensure_csrf_token,
    hash_password,
    validate_csrf,
    verify_password,
)
from common.utils import (
    atomic_to_xmr,
    parse_xmr_to_atomic,
    random_token,
    sanitize_filename,
    slugify,
    utcnow_iso,
    validate_relative_file,
)
from common.wallet_rpc import MoneroWalletRPC, WalletRPCError


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

settings: AdminSettings = load_admin_settings()
app = FastAPI(title="xmr-webshop-admin")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="admin_session",
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["format_xmr"] = atomic_to_xmr


def db_conn() -> sqlite3.Connection:
    return connect_db(settings.db_path)


def admin_redirect(request: Request):
    if not request.session.get("admin_user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


def template_context(request: Request, **extra: object) -> dict[str, object]:
    context = {
        "request": request,
        "csrf_token": ensure_csrf_token(request.session),
        "admin_username": request.session.get("admin_username"),
    }
    context.update(extra)
    return context


def ensure_admin_user(conn: sqlite3.Connection) -> None:
    password_hash = settings.admin_password_hash
    if not password_hash and settings.admin_password:
        password_hash = hash_password(settings.admin_password)

    if not password_hash:
        raise RuntimeError(
            "Set ADMIN_PASSWORD or ADMIN_PASSWORD_HASH before starting admin service"
        )

    row = conn.execute(
        "SELECT id FROM admin_users WHERE username = ?",
        (settings.admin_username,),
    ).fetchone()

    if row:
        return

    with conn:
        conn.execute(
            """
            INSERT INTO admin_users (username, password_hash, is_active, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (settings.admin_username, password_hash, utcnow_iso(), utcnow_iso()),
        )


@app.on_event("startup")
async def startup() -> None:
    Path(settings.digital_goods_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.product_images_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = db_conn()
    try:
        run_migrations(conn)
        ensure_admin_user(conn)
    finally:
        conn.close()

    app.state.wallet = MoneroWalletRPC(
        rpc_url=settings.wallet_rpc_url,
        username=settings.wallet_rpc_username,
        password=settings.wallet_rpc_password,
        wallet_file=settings.wallet_file,
        wallet_password=settings.wallet_password,
        wallet_auto_create=settings.wallet_auto_create,
        daemon_nodes=settings.monero_remote_nodes,
        wallet_create_language=settings.wallet_create_language,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    wallet = getattr(app.state, "wallet", None)
    if wallet is not None:
        await wallet.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login")
async def login_get(request: Request):
    if request.session.get("admin_user_id"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html", template_context(request, error=None)
    )


@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    conn = db_conn()
    try:
        row = conn.execute(
            """
            SELECT id, username, password_hash, is_active
            FROM admin_users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    finally:
        conn.close()

    if (
        not row
        or int(row["is_active"]) != 1
        or not verify_password(password, str(row["password_hash"]))
    ):
        return templates.TemplateResponse(
            "login.html",
            template_context(request, error="Invalid username or password"),
            status_code=400,
        )

    request.session["admin_user_id"] = int(row["id"])
    request.session["admin_username"] = str(row["username"])
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
async def dashboard(request: Request):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    conn = db_conn()
    try:
        counts = {
            "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "pending_payment": conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'pending_payment'"
            ).fetchone()[0],
            "waiting_confirmations": conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'waiting_confirmations'"
            ).fetchone()[0],
            "completed": conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'completed'"
            ).fetchone()[0],
            "expired": conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'expired'"
            ).fetchone()[0],
        }
    finally:
        conn.close()

    return templates.TemplateResponse(
        "dashboard.html", template_context(request, counts=counts)
    )


@app.get("/products")
async def products_list(request: Request):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    conn = db_conn()
    try:
        products = conn.execute(
            """
            SELECT id, slug, title, price_atomic, delivery_type, file_path, image_url, image_path, is_active, is_archived, updated_at
            FROM products
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "products.html", template_context(request, products=products)
    )


@app.get("/products/new")
async def product_new_get(request: Request):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        "product_form.html",
        template_context(
            request, product=None, error=None, form_action="/products/new"
        ),
    )


async def resolve_product_file(
    existing_path: str, upload: UploadFile | None, current_path: str = ""
) -> str:
    if upload and upload.filename:
        safe_name = sanitize_filename(upload.filename)
        final_name = f"{random_token(6)}-{safe_name}"
        target = Path(settings.digital_goods_dir) / final_name
        content = await upload.read()
        target.write_bytes(content)
        return final_name

    if existing_path.strip():
        return validate_relative_file(settings.digital_goods_dir, existing_path.strip())

    if current_path:
        return current_path

    raise ValueError("Provide an existing file path or upload a file")


async def resolve_product_image(
    image_url: str,
    upload_image: UploadFile | None,
    current_image_url: str = "",
    current_image_path: str = "",
) -> tuple[str, str]:
    if upload_image and upload_image.filename:
        safe_name = sanitize_filename(upload_image.filename)
        final_name = f"{random_token(6)}-{safe_name}"
        target = Path(settings.product_images_dir) / final_name
        content = await upload_image.read()
        target.write_bytes(content)
        return "", final_name

    clean_url = image_url.strip()
    if clean_url:
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            raise ValueError("Image URL must start with http:// or https://")
        return clean_url, ""

    if current_image_url or current_image_path:
        return current_image_url, current_image_path

    return "", ""


@app.post("/products/new")
async def product_new_post(
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    short_description: str = Form(...),
    long_description: str = Form(...),
    price_xmr: str = Form(...),
    delivery_type: str = Form("file"),
    existing_file_path: str = Form(""),
    upload_file: UploadFile | None = File(None),
    image_url: str = Form(""),
    upload_image: UploadFile | None = File(None),
    is_active: str | None = Form(None),
    csrf_token: str = Form(...),
):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    try:
        final_slug = slugify(slug or title)
        price_atomic = parse_xmr_to_atomic(price_xmr)
        file_path = await resolve_product_file(existing_file_path, upload_file)
        final_image_url, final_image_path = await resolve_product_image(
            image_url,
            upload_image,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "product_form.html",
            template_context(
                request,
                product=None,
                error=str(exc),
                form_action="/products/new",
            ),
            status_code=400,
        )

    now_iso = utcnow_iso()
    conn = db_conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO products (
                    slug,
                    title,
                    short_description,
                    long_description,
                    price_atomic,
                    delivery_type,
                    file_path,
                    image_url,
                    image_path,
                    is_active,
                    is_archived,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    final_slug,
                    title.strip(),
                    short_description.strip(),
                    long_description.strip(),
                    price_atomic,
                    delivery_type,
                    file_path,
                    final_image_url or None,
                    final_image_path or None,
                    1 if is_active else 0,
                    now_iso,
                    now_iso,
                ),
            )
    except sqlite3.IntegrityError:
        conn.close()
        return templates.TemplateResponse(
            "product_form.html",
            template_context(
                request,
                product=None,
                error="Slug already exists",
                form_action="/products/new",
            ),
            status_code=400,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return RedirectResponse(url="/products", status_code=303)


@app.get("/products/{product_id}/edit")
async def product_edit_get(request: Request, product_id: int):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    conn = db_conn()
    try:
        product = conn.execute(
            """
            SELECT id, slug, title, short_description, long_description, price_atomic,
                   delivery_type, file_path, image_url, image_path, is_active, is_archived
            FROM products
            WHERE id = ?
            """,
            (product_id,),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
    finally:
        conn.close()

    return templates.TemplateResponse(
        "product_form.html",
        template_context(
            request,
            product=product,
            error=None,
            form_action=f"/products/{product_id}/edit",
        ),
    )


@app.post("/products/{product_id}/edit")
async def product_edit_post(
    request: Request,
    product_id: int,
    title: str = Form(...),
    slug: str = Form(...),
    short_description: str = Form(...),
    long_description: str = Form(...),
    price_xmr: str = Form(...),
    delivery_type: str = Form("file"),
    existing_file_path: str = Form(""),
    upload_file: UploadFile | None = File(None),
    image_url: str = Form(""),
    upload_image: UploadFile | None = File(None),
    is_active: str | None = Form(None),
    is_archived: str | None = Form(None),
    csrf_token: str = Form(...),
):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    conn = db_conn()
    try:
        existing = conn.execute(
            "SELECT file_path, image_url, image_path FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")

        try:
            final_slug = slugify(slug)
            price_atomic = parse_xmr_to_atomic(price_xmr)
            file_path = await resolve_product_file(
                existing_file_path, upload_file, str(existing["file_path"])
            )
            final_image_url, final_image_path = await resolve_product_image(
                image_url,
                upload_image,
                str(existing["image_url"] or ""),
                str(existing["image_path"] or ""),
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                "product_form.html",
                template_context(
                    request,
                    product={
                        "id": product_id,
                        "slug": slug,
                        "title": title,
                        "short_description": short_description,
                        "long_description": long_description,
                        "price_atomic": 0,
                        "delivery_type": delivery_type,
                        "file_path": existing_file_path,
                        "image_url": image_url,
                        "image_path": str(existing["image_path"] or ""),
                        "is_active": 1 if is_active else 0,
                        "is_archived": 1 if is_archived else 0,
                    },
                    error=str(exc),
                    form_action=f"/products/{product_id}/edit",
                ),
                status_code=400,
            )

        with conn:
            conn.execute(
                """
                UPDATE products
                SET
                    slug = ?,
                    title = ?,
                    short_description = ?,
                    long_description = ?,
                    price_atomic = ?,
                    delivery_type = ?,
                    file_path = ?,
                    image_url = ?,
                    image_path = ?,
                    is_active = ?,
                    is_archived = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    final_slug,
                    title.strip(),
                    short_description.strip(),
                    long_description.strip(),
                    price_atomic,
                    delivery_type,
                    file_path,
                    final_image_url or None,
                    final_image_path or None,
                    1 if is_active else 0,
                    1 if is_archived else 0,
                    utcnow_iso(),
                    product_id,
                ),
            )
    except sqlite3.IntegrityError:
        return templates.TemplateResponse(
            "product_form.html",
            template_context(
                request,
                product=None,
                error="Slug already exists",
                form_action=f"/products/{product_id}/edit",
            ),
            status_code=400,
        )
    finally:
        conn.close()

    return RedirectResponse(url="/products", status_code=303)


@app.post("/products/{product_id}/archive")
async def product_archive(
    request: Request, product_id: int, csrf_token: str = Form(...)
):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    conn = db_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE products
                SET is_active = 0, is_archived = 1, updated_at = ?
                WHERE id = ?
                """,
                (utcnow_iso(), product_id),
            )
    finally:
        conn.close()
    return RedirectResponse(url="/products", status_code=303)


@app.post("/products/{product_id}/delete")
async def product_delete(
    request: Request, product_id: int, csrf_token: str = Form(...)
):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    conn = db_conn()
    try:
        linked = conn.execute(
            "SELECT COUNT(*) FROM order_items WHERE product_id = ?",
            (product_id,),
        ).fetchone()[0]

        with conn:
            if linked:
                conn.execute(
                    """
                    UPDATE products
                    SET is_active = 0, is_archived = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (utcnow_iso(), product_id),
                )
            else:
                conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    finally:
        conn.close()
    return RedirectResponse(url="/products", status_code=303)


@app.get("/orders")
async def orders_list(request: Request, status: str = ""):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    conn = db_conn()
    try:
        if status:
            orders = conn.execute(
                """
                SELECT id, public_token, status, total_atomic, confirmation_count, created_at, expires_at
                FROM orders
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                (status,),
            ).fetchall()
        else:
            orders = conn.execute(
                """
                SELECT id, public_token, status, total_atomic, confirmation_count, created_at, expires_at
                FROM orders
                ORDER BY created_at DESC
                """
            ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "orders.html",
        template_context(request, orders=orders, current_status=status),
    )


@app.get("/orders/{order_id}")
async def order_detail(request: Request, order_id: int):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    conn = db_conn()
    try:
        order = conn.execute(
            """
            SELECT
                o.*,
                p.payment_subaddress,
                p.requested_atomic,
                p.received_atomic,
                p.confirmation_count AS payment_confirmations,
                p.status AS payment_status,
                p.txid AS payment_txid
            FROM orders o
            LEFT JOIN payment_requests p ON p.order_id = o.id
            WHERE o.id = ?
            """,
            (order_id,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = conn.execute(
            """
            SELECT product_title, quantity, unit_price_atomic, delivery_ref
            FROM order_items
            WHERE order_id = ?
            ORDER BY id ASC
            """,
            (order_id,),
        ).fetchall()

        events = conn.execute(
            """
            SELECT event_type, detail, created_at
            FROM delivery_events
            WHERE order_id = ?
            ORDER BY created_at DESC
            """,
            (order_id,),
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "order_detail.html",
        template_context(request, order=order, items=items, events=events),
    )


@app.post("/orders/{order_id}/cancel")
async def order_cancel(request: Request, order_id: int, csrf_token: str = Form(...)):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect
    if not validate_csrf(request.session, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    conn = db_conn()
    try:
        with conn:
            conn.execute(
                """
                UPDATE orders
                SET status = 'cancelled', cancelled_at = ?, updated_at = ?
                WHERE id = ? AND status IN ('pending_payment', 'waiting_confirmations')
                """,
                (utcnow_iso(), utcnow_iso(), order_id),
            )
            conn.execute(
                """
                INSERT INTO delivery_events (order_id, event_type, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, "order_cancelled", "Cancelled by admin", utcnow_iso()),
            )
    finally:
        conn.close()

    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)


@app.get("/wallet")
async def wallet_view(request: Request):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    wallet: MoneroWalletRPC = app.state.wallet
    error = None
    balance = None
    addresses = None
    try:
        balance = await wallet.get_balance()
        addresses = await wallet.get_address()
    except WalletRPCError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        "wallet.html",
        template_context(request, balance=balance, addresses=addresses, error=error),
    )


@app.get("/analytics")
async def analytics_view(request: Request):
    redirect = admin_redirect(request)
    if redirect is not None:
        return redirect

    conn = db_conn()
    try:
        totals = conn.execute(
            """
            SELECT event_type, COUNT(*) AS total_count
            FROM analytics_events
            GROUP BY event_type
            ORDER BY total_count DESC
            """
        ).fetchall()

        daily = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, event_type, COUNT(*) AS total_count
            FROM analytics_events
            WHERE created_at >= datetime('now', '-30 day')
            GROUP BY day, event_type
            ORDER BY day DESC, event_type ASC
            """
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "analytics.html",
        template_context(request, totals=totals, daily=daily),
    )
