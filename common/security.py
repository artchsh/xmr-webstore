from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time


def hash_password(password: str, iterations: int = 310000) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iterations_str, salt_b64, digest_b64 = password_hash.split("$", 3)
    except ValueError:
        return False

    if algo != "pbkdf2_sha256":
        return False

    iterations = int(iterations_str)
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(expected, derived)


def ensure_csrf_token(session: dict) -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf(session: dict, submitted: str | None) -> bool:
    expected = session.get("csrf_token")
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


def generate_download_signature(
    secret: str, order_token: str, item_id: int, expires_at: int
) -> str:
    payload = f"{order_token}:{item_id}:{expires_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_download_signature(
    secret: str,
    order_token: str,
    item_id: int,
    expires_at: int,
    signature: str,
) -> bool:
    if expires_at < int(time.time()):
        return False
    expected = generate_download_signature(secret, order_token, item_id, expires_at)
    return hmac.compare_digest(expected, signature)
