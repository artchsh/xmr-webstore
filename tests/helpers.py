from __future__ import annotations

import re


def extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        raise AssertionError("CSRF token input not found in HTML")
    return match.group(1)


def extract_order_token(location: str) -> str:
    match = re.search(r"/order/([^/?#]+)", location)
    if not match:
        raise AssertionError(f"Order token not found in location: {location}")
    return match.group(1)


def extract_download_href(html: str) -> str:
    match = re.search(r'href="(/order/[^"]+/download/[^"]+)"', html)
    if not match:
        raise AssertionError("Download link not found")
    return match.group(1)
