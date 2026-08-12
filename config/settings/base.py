"""
Base settings shared by every environment.

Environment-specific values (databases, security hardening, hosts) live
in ``development.py`` and ``production.py`` and override these defaults.
"""
from pathlib import Path

import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-aknazar-dev-key-do-not-use-in-production",
)

DEBUG = bool(os.environ.get("DJANGO_DEBUG", "True") == "True")

ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project applications
    "apps.common",
    "apps.accounts",
    "apps.employees",
    "apps.finance",
    "apps.customers",
    "apps.services",
    "apps.billing",
    "apps.workentry",
    "apps.reports",
    "apps.pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Project middleware: keeps track of the current request user for audit
    # fields (created_by / updated_by / deleted_by) on every model.
    "apps.common.middleware.CurrentUserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.erp_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "pages:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Money / decimals: single source of truth for financial precision.
# All monetary fields across the ERP must use these widths.
# ---------------------------------------------------------------------------
MONEY_MAX_DIGITS = 18
MONEY_DECIMAL_PLACES = 2

# ---------------------------------------------------------------------------
# Application metadata (exposed to templates via erp_context processor)
# ---------------------------------------------------------------------------
ERP_APP_NAME = "AK Nazar Cyber Cafe ERP"
ERP_APP_VERSION = "1.0.0"
ERP_COMPANY_NAME = "AK Nazar Cyber Cafe"
ERP_COMPANY_ADDRESS = ""

# ---------------------------------------------------------------------------
# Security defaults (strengthened in production.py)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Origins permitted to send state-changing requests. Django 5 verifies the
# Origin header on every non-safe request, so any frontend that terminates
# HTTPS before Django (reverse proxy, preview tunnel) MUST list its origins
# here. Values come from the environment (comma separated) and each
# environment may extend or replace the defaults.
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Authentication throttling (accounts.services.authentication_service)
# ---------------------------------------------------------------------------
LOGIN_ATTEMPT_THRESHOLD = 5
LOGIN_LOCKOUT_SECONDS = 300
