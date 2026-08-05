"""
Authentication service — login throttling / account lockout.

Protects the login endpoint against brute-force guessing. Failed attempts
are counted per username using Django's cache.

Note on production: the locmem cache is fine for a single worker process.
When the ERP is deployed with multiple gunicorn workers or scaled out,
switch CACHES to a shared store (Redis) so the counter is consistent
across processes.
"""
from django.conf import settings
from django.core.cache import cache


def _cache_key(username: str) -> str:
    return f"aknazar:login-attempts:{str(username).strip().lower()}"


def record_failed_attempt(username: str) -> int:
    """Increment the failure counter and return the new total."""
    key = _cache_key(username)
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, timeout=settings.LOGIN_LOCKOUT_SECONDS)
    return attempts


def is_locked_out(username: str) -> bool:
    """True when the user has exceeded the allowed failure threshold."""
    attempts = cache.get(_cache_key(username), 0)
    return attempts >= settings.LOGIN_ATTEMPT_THRESHOLD


def clear_failed_attempts(username: str) -> None:
    """Reset the counter after a successful login."""
    cache.delete(_cache_key(username))
