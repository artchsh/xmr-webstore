from __future__ import annotations

import pytest

from tests.helpers import extract_csrf_token, extract_download_href


pytestmark = [pytest.mark.webshop]


def test_homepage_renders_expected_ssr_elements(webshop_client, create_product) -> None:
    create_product(slug="alpha", title="Alpha Pack", price_atomic=1_500_000_000_000)
    response = webshop_client.get("/")

    assert response.status_code == 200
    assert "Alpha Pack" in response.text
    assert "1.5 XMR" in response.text
    assert '<form method="post" action="/cart/add">' in response.text
    assert 'name="csrf_token"' in response.text


def test_product_page_and_checkout_render_without_required_javascript(
    webshop_client,
    create_product,
) -> None:
    product_id = create_product(slug="beta", title="Beta Bundle")

    detail = webshop_client.get("/product/beta")
    assert detail.status_code == 200
    assert f'name="product_id" value="{product_id}"' in detail.text
    assert '<input type="number" name="quantity"' in detail.text
    assert "<script" not in detail.text.lower()

    csrf = extract_csrf_token(detail.text)
    webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 3, "csrf_token": csrf},
        follow_redirects=False,
    )
    checkout = webshop_client.get("/checkout")
    assert checkout.status_code == 200
    assert "Total to pay: 3 XMR" in checkout.text
    assert '<form method="post" action="/checkout">' in checkout.text
    assert "<script" not in checkout.text.lower()


def test_order_page_status_messages_and_download_visibility(
    webshop_client,
    create_order,
) -> None:
    pending = create_order(status="pending_payment")
    completed = create_order(status="completed")
    expired = create_order(status="expired")

    pending_page = webshop_client.get(f"/order/{pending['token']}")
    assert "Monero Payment Instructions" in pending_page.text
    assert "/download/" not in pending_page.text

    completed_page = webshop_client.get(f"/order/{completed['token']}")
    assert "Payment confirmed" in completed_page.text
    download_href = extract_download_href(completed_page.text)
    assert (
        f"/order/{completed['token']}/download/{completed['item_id']}" in download_href
    )

    expired_page = webshop_client.get(f"/order/{expired['token']}")
    assert "This order expired before full payment was received." in expired_page.text


def test_cart_ssr_contains_forms_and_totals(webshop_client, create_product) -> None:
    product_id = create_product(title="Cart SSR")
    csrf = extract_csrf_token(webshop_client.get("/").text)

    webshop_client.post(
        "/cart/add",
        data={"product_id": product_id, "quantity": 2, "csrf_token": csrf},
        follow_redirects=False,
    )

    cart = webshop_client.get("/cart")
    assert cart.status_code == 200
    assert "Cart SSR" in cart.text
    assert "Total: 2 XMR" in cart.text
    assert '<form method="post" action="/cart/update"' in cart.text
    assert '<form method="post" action="/cart/clear">' in cart.text


def test_product_image_url_renders_in_storefront(
    webshop_client,
    sqlite_conn,
    create_product,
) -> None:
    product_id = create_product(title="Image Product")
    with sqlite_conn:
        sqlite_conn.execute(
            "UPDATE products SET image_url = ? WHERE id = ?",
            ("https://example.com/image.png", product_id),
        )

    response = webshop_client.get("/")
    assert response.status_code == 200
    assert 'src="https://example.com/image.png"' in response.text
