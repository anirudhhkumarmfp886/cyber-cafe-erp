"""Development settings: SQLite, DEBUG on, permissive hosts."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, CSRF_TRUSTED_ORIGINS  # noqa: F401

DEBUG = True

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# The online preview tunnel terminates HTTPS and forwards plain HTTP, so the
# Origin header seen by Django is "https://<preview-domain>" while the request
# itself is http. Trust the preview domain (and anything configured via env).
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [
        "https://*.monkeycode-ai.live",
        "http://*.monkeycode-ai.live",
    ]

# The preview proxy forwards the original scheme in X-Forwarded-Proto; tell
# Django about it so request.is_secure() is correct behind the tunnel.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
