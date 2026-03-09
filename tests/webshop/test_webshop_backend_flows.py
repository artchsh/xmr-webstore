from __future__ import annotations

import sqlite3
import time

import pytest

from common.security import generate_download_signature
from tests.helpers import extract_csrf_token, extract_download_href, extract_order_token


pytestmark = [pytest.mark.webshop]


def test_homepage_and_product_detail_load(
    webshop_client,
    create_product,
) -> None:
    product_id = create_product(slug="ebook-1", title="Privacy eBook")

    home = webshop_client.get("/")
    assert home.status_code == 200
    assert "text/html" in home.headers["content-type"]
    assert "Privacy eBook" in home.text

    detail = webshop_client.get("/product/ebook-1")
    assert detail.status_code == 200
    assert "Add to cart" in detail.text
    assert f'name="product_id" value="{product_id}"' in detail.text


def test_invalid_product_slug_returns_404(webshop_client) -> None:
    response = webshop_client.get("/product/does-not-exist")
    assert response.status_code == 404


def test_add_update_remove_cart_flow(webshop_client, create_product) -> None:
    product_id = create_product(title="Download Pack", price_atomic=2_000_000_000_000)

    home = webshop_client.get("/")
    csrf = extract_csrf_token(home.text)

    add = webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 2, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert add.status_code == 303
    assert add.headers["location"] == "/cart"

    cart = webshop_client.get("/cart")
    assert cart.status_code == 200
    assert "Download Pack" in cart.text
    assert "Total: 4 XMR" in cart.text

    csrf = extract_csrf_token(cart.text)
    remove = webshop_client.post(
        "/cart/update",
        data={"product_id": product_id, "quantity": 0, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert remove.status_code == 303

    after_remove = webshop_client.get("/cart")
    assert "Your cart is empty." in after_remove.text


def test_cart_persists_in_session_between_requests(
    webshop_client, create_product
) -> None:
    product_id = create_product(title="Session Product")

    csrf = extract_csrf_token(webshop_client.get("/").text)
    webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 1, "csrf_token": csrf},
        follow_redirects=False,
    )

    first = webshop_client.get("/cart")
    second = webshop_client.get("/cart")
    assert "Session Product" in first.text
    assert "Session Product" in second.text


def test_checkout_creates_order_and_payment_records(
    webshop_client,
    webshop_wallet,
    sqlite_conn: sqlite3.Connection,
    create_product,
) -> None:
    product_id = create_product(title="Checkout Product")

    csrf = extract_csrf_token(webshop_client.get("/").text)
    webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 1, "csrf_token": csrf},
        follow_redirects=False,
    )

    checkout_page = webshop_client.get("/checkout")
    assert checkout_page.status_code == 200
    csrf = extract_csrf_token(checkout_page.text)

    response = webshop_client.post(
        "/checkout",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/order/")
    order_token = extract_order_token(response.headers["location"])

    order = sqlite_conn.execute(
        "SELECT status, total_atomic, payment_subaddress FROM orders WHERE public_token = ?",
        (order_token,),
    ).fetchone()
    payment = sqlite_conn.execute(
        "SELECT status, requested_atomic FROM payment_requests WHERE order_id = (SELECT id FROM orders WHERE public_token = ?)",
        (order_token,),
    ).fetchone()

    assert order["status"] == "pending_payment"
    assert int(order["total_atomic"]) == 1_000_000_000_000
    assert str(order["payment_subaddress"]).startswith("84FakeSubAddress")
    assert payment["status"] == "pending"
    assert int(payment["requested_atomic"]) == 1_000_000_000_000
    assert webshop_wallet.created_labels


def test_checkout_wallet_failure_returns_503(
    webshop_client,
    webshop_wallet,
    sqlite_conn: sqlite3.Connection,
    create_product,
) -> None:
    product_id = create_product(title="Unlucky Product")
    webshop_wallet.raise_on_create_subaddress = True

    csrf = extract_csrf_token(webshop_client.get("/").text)
    webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 1, "csrf_token": csrf},
        follow_redirects=False,
    )

    checkout_page = webshop_client.get("/checkout")
    csrf = extract_csrf_token(checkout_page.text)
    response = webshop_client.post("/checkout", data={"csrf_token": csrf})

    assert response.status_code == 503
    assert sqlite_conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_order_pages_and_invalid_token_behavior(
    webshop_client,
    create_order,
) -> None:
    order = create_order(status="pending_payment")

    valid = webshop_client.get(f"/order/{order['token']}")
    assert valid.status_code == 200
    assert "Monero Payment Instructions" in valid.text

    invalid = webshop_client.get("/order/not-a-real-token")
    assert invalid.status_code == 404


def test_order_display_changes_by_status(webshop_client, create_order) -> None:
    pending = create_order(status="pending_payment")
    completed = create_order(status="completed")

    pending_page = webshop_client.get(f"/order/{pending['token']}")
    assert "Send exactly" in pending_page.text
    assert "/download/" not in pending_page.text

    completed_page = webshop_client.get(f"/order/{completed['token']}")
    assert "Payment confirmed" in completed_page.text
    assert "Download" in completed_page.text


def test_receipt_text_download(webshop_client, create_order) -> None:
    order = create_order(status="completed")
    response = webshop_client.get(f"/order/{order['token']}/receipt.txt")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "attachment; filename=receipt-" in response.headers["content-disposition"]
    assert "xmr-webshop receipt" in response.text
    assert f"order_token: {order['token']}" in response.text


def test_download_requires_valid_signature(
    webshop_client,
    create_order,
    app_env,
) -> None:
    order = create_order(status="completed")
    expires = int(time.time()) + 120

    bad = webshop_client.get(
        f"/order/{order['token']}/download/{order['item_id']}?exp={expires}&sig=bad"
    )
    assert bad.status_code == 403

    signature = generate_download_signature(
        app_env["download_token_secret"],
        order["token"],
        order["item_id"],
        expires,
    )
    good = webshop_client.get(
        f"/order/{order['token']}/download/{order['item_id']}?exp={expires}&sig={signature}"
    )
    assert good.status_code == 200
    assert "application/octet-stream" in good.headers["content-type"]


def test_download_blocked_when_order_not_paid(
    webshop_client,
    create_order,
    app_env,
) -> None:
    order = create_order(status="pending_payment")
    expires = int(time.time()) + 120
    signature = generate_download_signature(
        app_env["download_token_secret"],
        order["token"],
        order["item_id"],
        expires,
    )

    response = webshop_client.get(
        f"/order/{order['token']}/download/{order['item_id']}?exp={expires}&sig={signature}"
    )
    assert response.status_code == 403
    assert "Order is not paid" in response.text


def test_invalid_form_inputs_are_rejected(webshop_client, create_product) -> None:
    product_id = create_product()
    csrf = extract_csrf_token(webshop_client.get("/").text)

    bad_csrf = webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 1, "csrf_token": "invalid"},
    )
    assert bad_csrf.status_code == 400

    missing_product = webshop_client.post(
        "/cart/add",
        data={"quantity": 1, "csrf_token": csrf},
    )
    assert missing_product.status_code == 422


def test_public_flow_is_html_form_based(webshop_client, create_product) -> None:
    create_product(title="SSR Product")
    response = webshop_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<form method="post" action="/cart/add">' in response.text
    assert "fetch(" not in response.text


def test_storefront_search_filters_products(webshop_client, create_product) -> None:
    create_product(slug="alpha", title="Alpha Bundle")
    create_product(slug="beta", title="Beta Bundle")

    response = webshop_client.get("/?q=alpha")
    assert response.status_code == 200
    assert "Alpha Bundle" in response.text
    assert "Beta Bundle" not in response.text
