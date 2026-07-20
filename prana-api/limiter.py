"""Shared SlowAPI rate-limiter instance.

Import `limiter` in routers to apply @limiter.limit() decorators.
Register in main.py: app.state.limiter = limiter + RateLimitExceeded handler.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_key(request) -> str:
    """
    Rate-limit key = the real client IP (finding H1/H3).

    Behind Kong/ALB, request.client.host is the proxy — keying on it would pool every
    user into one bucket. Use the rightmost X-Forwarded-For entry (appended by our
    trusted proxy); ignore attacker-supplied leftmost entries. Falls back to the peer.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return get_remote_address(request)


limiter = Limiter(key_func=_client_key)
