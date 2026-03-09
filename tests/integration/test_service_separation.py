from __future__ import annotations

import pytest

from tests.helpers import extract_csrf_token


pytestmark = [pytest.mark.integration]


def test_webshop_and_admin_expose_different_route_surfaces(
    webshop_client,
    admin_client,
) -> None:
    assert webshop_client.get("/health").status_code == 200
    assert admin_client.get("/health").status_code == 200

    assert webshop_client.get("/login").status_code == 404
    assert admin_client.get("/checkout").status_code == 404


def test_admin_created_product_is_visible_in_webshop(
    admin_client_logged_in,
    webshop_client,
) -> None:
    product_form = admin_client_logged_in.get("/products/new")
    csrf = extract_csrf_token(product_form.text)
    create = admin_client_logged_in.post(
        "/products/new",
        data={
            "title": "Cross Service Product",
            "slug": "cross-service-product",
            "short_description": "shared db",
            "long_description": "shared db long",
            "price_xmr": "3",
            "delivery_type": "file",
            "existing_file_path": "",
            "is_active": "1",
            "csrf_token": csrf,
        },
        files={"upload_file": ("cross-service.txt", b"payload", "text/plain")},
        follow_redirects=False,
    )
    assert create.status_code == 303

    storefront = webshop_client.get("/")
    assert storefront.status_code == 200
    assert "Cross Service Product" in storefront.text
