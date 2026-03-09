from __future__ import annotations

import time

import pytest

from common.security import generate_download_signature


pytestmark = [pytest.mark.security]


def test_template_escaping_prevents_script_injection(
    webshop_client, create_product
) -> None:
    create_product(
        slug="xss-product",
        title="<script>alert('x')</script>",
        short_description="<b>short</b>",
        long_description="<img src=x onerror=alert(1)>",
    )

    response = webshop_client.get("/")
    assert response.status_code == 200
    assert "<script>alert('x')</script>" not in response.text
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;" in response.text


def test_malformed_session_cookie_is_handled_safely(webshop_client) -> None:
    webshop_client.cookies.set("shop_session", "malformed-session-cookie")
    response = webshop_client.get("/cart")
    assert response.status_code == 200
    assert "Your cart is empty." in response.text


def test_invalid_order_tokens_fail_safely(webshop_client) -> None:
    response = webshop_client.get("/order/../../etc/passwd")
    assert response.status_code in {404, 422}


def test_disallow_download_before_payment_even_with_signature(
    webshop_client,
    create_order,
    app_env,
) -> None:
    order = create_order(status="pending_payment")
    exp = int(time.time()) + 120
    sig = generate_download_signature(
        app_env["download_token_secret"], order["token"], order["item_id"], exp
    )

    response = webshop_client.get(
        f"/order/{order['token']}/download/{order['item_id']}?exp={exp}&sig={sig}"
    )
    assert response.status_code == 403


def test_admin_auth_protection_blocks_sensitive_pages(admin_client) -> None:
    for path in ["/products", "/orders", "/wallet", "/analytics"]:
        response = admin_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_admin_product_existing_file_path_blocks_traversal(
    admin_client_logged_in,
) -> None:
    page = admin_client_logged_in.get("/products/new")
    csrf = page.text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]

    response = admin_client_logged_in.post(
        "/products/new",
        data={
            "title": "Traversal",
            "slug": "traversal",
            "short_description": "short",
            "long_description": "long",
            "price_xmr": "1",
            "delivery_type": "file",
            "existing_file_path": "../secret.txt",
            "csrf_token": csrf,
        },
        files={"_multipart": ("dummy.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400
    assert "escapes digital goods directory" in response.text


def test_internal_routes_not_cross_exposed(webshop_client, admin_client) -> None:
    assert webshop_client.get("/login").status_code == 404
    assert admin_client.get("/checkout").status_code == 404


def test_csrf_enforced_on_webshop_cart_form(webshop_client, create_product) -> None:
    product_id = create_product()
    response = webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 1, "csrf_token": "bad"},
    )
    assert response.status_code == 400
