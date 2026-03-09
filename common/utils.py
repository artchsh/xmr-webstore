from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import secrets
from pathlib import Path


ATOMIC_UNITS = decimal.Decimal("1000000000000")


def utcnow() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def utcnow_iso() -> str:
    return utcnow().replace(microsecond=0).isoformat()


def parse_iso(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_xmr_to_atomic(raw: str) -> int:
    raw = raw.strip()
    if not raw:
        raise ValueError("Price is required")
    try:
        amount = decimal.Decimal(raw)
    except decimal.InvalidOperation as exc:
        raise ValueError("Invalid price format") from exc
    if amount <= 0:
        raise ValueError("Price must be positive")
    amount_atomic = amount * ATOMIC_UNITS
    if amount_atomic != amount_atomic.to_integral_value():
        raise ValueError("Price supports up to 12 decimal places")
    atomic = int(amount_atomic)
    if atomic <= 0:
        raise ValueError("Price must be positive")
    return atomic


def atomic_to_xmr(amount_atomic: int) -> str:
    amount = decimal.Decimal(amount_atomic) / ATOMIC_UNITS
    return f"{amount:.12f}".rstrip("0").rstrip(".")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    if not value:
        raise ValueError("Slug cannot be empty")
    return value


def random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if not name:
        raise ValueError("Invalid filename")
    return name


def validate_relative_file(base_dir: str, relative_path: str) -> str:
    if not relative_path:
        raise ValueError("File path is required")

    base = Path(base_dir).resolve()
    candidate = (base / relative_path).resolve()

    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError("File path escapes digital goods directory")
    if not candidate.is_file():
        raise ValueError("File does not exist")

    return str(relative)
