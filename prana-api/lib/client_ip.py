"""Spoof-resistant client-IP resolution (finding H3).

X-Forwarded-For is a comma-separated chain: each proxy appends the address it
received the connection from, on the RIGHT. So the entries our own trusted proxies
(Kong, optionally ALB) added are the rightmost ones; everything to their left is
client-controllable and must never be trusted for audit logging or rate limiting.
"""
from typing import Optional


def get_client_ip(request, trusted_proxy_count: int = 1) -> str:
    """
    Return the real client IP as observed by our trusted proxy layer.

    We take the entry `trusted_proxy_count` positions from the right of the
    X-Forwarded-For chain. If the chain has fewer entries than that (so a
    trusted value can't be located), fall back to the raw socket peer rather
    than trusting an attacker-supplied value.
    """
    xff: Optional[str] = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= trusted_proxy_count >= 1:
            return parts[-trusted_proxy_count]
    client = getattr(request, "client", None)
    return client.host if client and getattr(client, "host", None) else "unknown"
