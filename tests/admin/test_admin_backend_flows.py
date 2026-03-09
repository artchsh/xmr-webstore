from __future__ import annotations

import sqlite3

import pytest

from tests.helpers import extract_csrf_token


pytestmark = [pytest.mark.admin]


def test_unauthorized_admin_routes_redirect_to_login(admin_client) -> None:
    for path in ["/", "/products", "/orders", "/wallet", "/analytics"]:
        response = admin_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_admin_login_logout_flow(admin_client, app_env) -> None:
    login_page = admin_client.get("/login")
    csrf = extract_csrf_token(login_page.text)

    login = admin_client.post(
        "/login",
        data={
            "username": app_env["admin_username"],
            "password": app_env["admin_password"],
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/"

    dashboard = admin_client.get("/")
    assert dashboard.status_code == 200
    assert "Dashboard" in dashboard.text

    csrf = extract_csrf_token(dashboard.text)
    logout = admin_client.post(
        "/logout",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"


def test_admin_login_rejects_invalid_credentials(admin_client, app_env) -> None:
    login_page = admin_client.get("/login")
    csrf = extract_csrf_token(login_page.text)

    response = admin_client.post(
        "/login",
        data={
            "username": app_env["admin_username"],
            "password": "wrong-password",
            "csrf_token": csrf,
        },
    )
    assert response.status_code == 400
    assert "Invalid username or password" in response.text


def test_admin_login_csrf_is_enforced(admin_client, app_env) -> None:
    response = admin_client.post(
        "/login",
        data={
            "username": app_env["admin_username"],
            "password": app_env["admin_password"],
            "csrf_token": "invalid",
        },
    )
    assert response.status_code == 400


def test_product_create_edit_archive_flow(
    admin_client_logged_in,
    sqlite_conn: sqlite3.Connection,
) -> None:
    new_page = admin_client_logged_in.get("/products/new")
    csrf = extract_csrf_token(new_page.text)

    create = admin_client_logged_in.post(
        "/products/new",
        data={
            "title": "Admin Product",
            "slug": "admin-product",
            "short_description": "short",
            "long_description": "long",
            "price_xmr": "1.25",
            "delivery_type": "file",
            "existing_file_path": "",
            "is_active": "1",
            "csrf_token": csrf,
        },
        files={"upload_file": ("admin-file.txt", b"admin payload", "text/plain")},
        follow_redirects=False,
    )
    assert create.status_code == 303
    assert create.headers["location"] == "/products"

    product = sqlite_conn.execute(
        "SELECT id, title, slug, price_atomic, file_path FROM products WHERE slug = 'admin-product'"
    ).fetchone()
    assert product is not None
    assert product["title"] == "Admin Product"
    assert int(product["price_atomic"]) == 1_250_000_000_000
    assert product["file_path"]

    edit_page = admin_client_logged_in.get(f"/products/{product['id']}/edit")
    csrf = extract_csrf_token(edit_page.text)
    edit = admin_client_logged_in.post(
        f"/products/{product['id']}/edit",
        data={
            "title": "Admin Product Updated",
            "slug": "admin-product-updated",
            "short_description": "short2",
            "long_description": "long2",
            "price_xmr": "2.5",
            "delivery_type": "file",
            "existing_file_path": product["file_path"],
            "is_active": "1",
            "is_archived": "",
            "csrf_token": csrf,
        },
        files={"_multipart": ("dummy.txt", b"x", "text/plain")},
        follow_redirects=False,
    )
    assert edit.status_code == 303

    updated = sqlite_conn.execute(
        "SELECT title, slug, price_atomic FROM products WHERE id = ?",
        (product["id"],),
    ).fetchone()
    assert updated["title"] == "Admin Product Updated"
    assert updated["slug"] == "admin-product-updated"
    assert int(updated["price_atomic"]) == 2_500_000_000_000

    products_page = admin_client_logged_in.get("/products")
    csrf = extract_csrf_token(products_page.text)
    archive = admin_client_logged_in.post(
        f"/products/{product['id']}/archive",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert archive.status_code == 303

    archived = sqlite_conn.execute(
        "SELECT is_active, is_archived FROM products WHERE id = ?", (product["id"],)
    ).fetchone()
    assert int(archived["is_active"]) == 0
    assert int(archived["is_archived"]) == 1


def test_product_delete_with_linked_order_archives_not_hard_deletes(
    admin_client_logged_in,
    sqlite_conn: sqlite3.Connection,
    create_product,
    create_order,
) -> None:
    product_id = create_product(slug="delete-linked", title="Delete Linked")
    create_order(product_id=product_id)

    products_page = admin_client_logged_in.get("/products")
    csrf = extract_csrf_token(products_page.text)
    response = admin_client_logged_in.post(
        f"/products/{product_id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303

    row = sqlite_conn.execute(
        "SELECT is_active, is_archived FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    assert row is not None
    assert int(row["is_active"]) == 0
    assert int(row["is_archived"]) == 1


def test_orders_list_and_order_detail_pages(
    admin_client_logged_in,
    create_order,
) -> None:
    pending = create_order(status="pending_payment")
    completed = create_order(status="completed")

    list_page = admin_client_logged_in.get("/orders")
    assert list_page.status_code == 200
    assert pending["token"] in list_page.text
    assert completed["token"] in list_page.text

    filtered = admin_client_logged_in.get("/orders?status=completed")
    assert filtered.status_code == 200
    assert completed["token"] in filtered.text
    assert pending["token"] not in filtered.text

    detail = admin_client_logged_in.get(f"/orders/{completed['order_id']}")
    assert detail.status_code == 200
    assert "Payment state:" in detail.text
    assert completed["payment_subaddress"] in detail.text


def test_admin_product_search_filters_results(
    admin_client_logged_in,
    create_product,
) -> None:
    create_product(slug="alpha-admin", title="Alpha Admin Product")
    create_product(slug="beta-admin", title="Beta Admin Product")

    response = admin_client_logged_in.get("/products?q=alpha")
    assert response.status_code == 200
    assert "Alpha Admin Product" in response.text
    assert "Beta Admin Product" not in response.text


def test_order_cancel_action(
    admin_client_logged_in,
    sqlite_conn: sqlite3.Connection,
    create_order,
) -> None:
    order = create_order(status="pending_payment")
    detail = admin_client_logged_in.get(f"/orders/{order['order_id']}")
    csrf = extract_csrf_token(detail.text)

    response = admin_client_logged_in.post(
        f"/orders/{order['order_id']}/cancel",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303

    status = sqlite_conn.execute(
        "SELECT status FROM orders WHERE id = ?", (order["order_id"],)
    ).fetchone()[0]
    assert status == "cancelled"


def test_wallet_view_uses_mocked_wallet_data(
    admin_client_logged_in, admin_wallet
) -> None:
    admin_wallet.balance = {
        "balance": 2_500_000_000_000,
        "unlocked_balance": 2_000_000_000_000,
    }
    admin_wallet.addresses = {"address": "48WalletAddressForAdmin"}

    response = admin_client_logged_in.get("/wallet")
    assert response.status_code == 200
    assert "Total balance: 2.5 XMR" in response.text
    assert "Unlocked balance: 2 XMR" in response.text
    assert "48WalletAddressForAdmin" in response.text


def test_wallet_view_handles_wallet_errors(
    admin_client_logged_in, admin_wallet
) -> None:
    admin_wallet.raise_on_get_balance = True

    response = admin_client_logged_in.get("/wallet")
    assert response.status_code == 200
    assert "mocked wallet balance failure" in response.text


def test_invalid_product_form_input_returns_clean_error(admin_client_logged_in) -> None:
    new_page = admin_client_logged_in.get("/products/new")
    csrf = extract_csrf_token(new_page.text)

    response = admin_client_logged_in.post(
        "/products/new",
        data={
            "title": "Bad Product",
            "slug": "bad-product",
            "short_description": "short",
            "long_description": "long",
            "price_xmr": "not-a-number",
            "delivery_type": "file",
            "existing_file_path": "",
            "csrf_token": csrf,
        },
        files={"_multipart": ("dummy.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400
    assert "Invalid price format" in response.text


def test_csrf_enforced_on_admin_product_create(admin_client_logged_in) -> None:
    response = admin_client_logged_in.post(
        "/products/new",
        data={
            "title": "No CSRF",
            "slug": "no-csrf",
            "short_description": "short",
            "long_description": "long",
            "price_xmr": "1",
            "delivery_type": "file",
            "existing_file_path": "",
            "csrf_token": "wrong-token",
        },
        files={"upload_file": ("x.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400


def test_admin_product_image_url_saved(
    admin_client_logged_in,
    sqlite_conn: sqlite3.Connection,
) -> None:
    page = admin_client_logged_in.get("/products/new")
    csrf = extract_csrf_token(page.text)

    response = admin_client_logged_in.post(
        "/products/new",
        data={
            "title": "Image URL Product",
            "slug": "image-url-product",
            "short_description": "short",
            "long_description": "long",
            "price_xmr": "1",
            "delivery_type": "file",
            "existing_file_path": "",
            "image_url": "https://example.com/product.png",
            "csrf_token": csrf,
        },
        files={"upload_file": ("file.txt", b"x", "text/plain")},
        follow_redirects=False,
    )
    assert response.status_code == 303

    row = sqlite_conn.execute(
        "SELECT image_url, image_path FROM products WHERE slug = ?",
        ("image-url-product",),
    ).fetchone()
    assert row["image_url"] == "https://example.com/product.png"
    assert row["image_path"] is None


def test_admin_settings_update_branding(
    admin_client_logged_in,
    sqlite_conn: sqlite3.Connection,
) -> None:
    page = admin_client_logged_in.get("/settings")
    assert page.status_code == 200
    csrf = extract_csrf_token(page.text)

    response = admin_client_logged_in.post(
        "/settings",
        data={
            "shop_name": "Privacy Bazaar",
            "shop_owner": "Anonymous Seller",
            "shop_logo_url": "https://example.com/logo.png",
            "csrf_token": csrf,
        },
        files={"_multipart": ("dummy.txt", b"x", "text/plain")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings"

    values = {
        row["setting_key"]: row["setting_value"]
        for row in sqlite_conn.execute(
            "SELECT setting_key, setting_value FROM shop_settings"
        ).fetchall()
    }
    assert values["shop_name"] == "Privacy Bazaar"
    assert values["shop_owner"] == "Anonymous Seller"
    assert values["shop_logo_url"] == "https://example.com/logo.png"
