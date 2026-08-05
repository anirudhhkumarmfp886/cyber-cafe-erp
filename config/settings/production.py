"""
Production settings: PostgreSQL, DEBUG off, hardened security.

Every value that must differ between environments is read from the
environment. The application refuses to boot when critical values
(SECRET_KEY, database credentials) are missing.
"""
import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR  # noqa: F401

DEBUG = False

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

# CSRF_TRUSTED_ORIGINS is inherited from base.py (reads
# DJANGO_CSRF_TRUSTED_ORIGINS). In production it MUST include the public
# origin(s), e.g. "https://erp.aknazar.in,https://www.aknazar.in".

# Hashed, compressed static files for cache busting (requires collectstatic).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 10},
    }
}

# ---------------------------------------------------------------------------
# Production hardening
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
