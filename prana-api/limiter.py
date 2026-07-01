"""Shared SlowAPI rate-limiter instance.

Import `limiter` in routers to apply @limiter.limit() decorators.
Register in main.py: app.state.limiter = limiter + RateLimitExceeded handler.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
