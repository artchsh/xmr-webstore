from __future__ import annotations

import time
from pathlib import Path

import pytest

from common.security import (
    ensure_csrf_token,
    generate_download_signature,
    hash_password,
    validate_csrf,
    verify_download_signature,
    verify_password,
)
from common.utils import parse_xmr_to_atomic, slugify, validate_relative_file
from services.webshop.main import get_cart


pytestmark = [pytest.mark.unit]


def test_password_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_csrf_token_generation_and_validation() -> None:
    session: dict = {}
    token = ensure_csrf_token(session)
    assert token
    assert validate_csrf(session, token)
    assert not validate_csrf(session, "invalid")
    assert not validate_csrf({}, token)


def test_download_signature_verification_expiry() -> None:
    secret = "secret"
    future = int(time.time()) + 60
    signature = generate_download_signature(secret, "order-token", 10, future)
    assert verify_download_signature(secret, "order-token", 10, future, signature)

    expired = int(time.time()) - 10
    expired_signature = generate_download_signature(secret, "order-token", 10, expired)
    assert not verify_download_signature(
        secret, "order-token", 10, expired, expired_signature
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", 1_000_000_000_000),
        ("0.5", 500_000_000_000),
        ("1.000000000001", 1_000_000_000_001),
    ],
)
def test_parse_xmr_to_atomic_valid(raw: str, expected: int) -> None:
    assert parse_xmr_to_atomic(raw) == expected


@pytest.mark.parametrize("raw", ["", "0", "-1", "1.0000000000001", "abc"])
def test_parse_xmr_to_atomic_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_xmr_to_atomic(raw)


def test_slugify_normalizes_input() -> None:
    assert slugify("  Hello, World  ") == "hello-world"


def test_validate_relative_file_blocks_path_escape(tmp_path: Path) -> None:
    base_dir = tmp_path / "goods"
    base_dir.mkdir()
    (base_dir / "safe.txt").write_text("ok")

    assert validate_relative_file(str(base_dir), "safe.txt") == "safe.txt"

    with pytest.raises(ValueError):
        validate_relative_file(str(base_dir), "../outside.txt")


def test_get_cart_sanitizes_malformed_session() -> None:
    class DummyRequest:
        def __init__(self, session: dict) -> None:
            self.session = session

    assert get_cart(DummyRequest({"cart": "not-a-dict"})) == {}
    assert get_cart(DummyRequest({"cart": {"1": "2", "2": -1, "x": "bad"}})) == {"1": 2}
