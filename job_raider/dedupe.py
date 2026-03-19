"""
Opportunity identity (`dedupe_id`) from normalized URL.

Implements architecture §8.1:
- Parse URL, lowercase scheme/host, strip fragment, drop default ports.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def compute_dedupe_id(url: str) -> str:
    """
    Return a stable string used as `dedupe_id` / merge key.

    Raises ValueError if URL is not an absolute http(s) URL with a host.
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Not an absolute URL with host: {url!r}")
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got {scheme!r}")
    host = parsed.hostname.lower()

    if parsed.port is None:
        host_with_port = host
    elif (scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443):
        host_with_port = host
    else:
        host_with_port = f"{host}:{parsed.port}"

    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f"{userinfo}:{parsed.password}"
        netloc = f"{userinfo}@{host_with_port}"
    else:
        netloc = host_with_port

    return urlunparse(
        (
            scheme,
            netloc,
            parsed.path or "",
            parsed.params,
            parsed.query,
            "",  # strip fragment
        )
    )
