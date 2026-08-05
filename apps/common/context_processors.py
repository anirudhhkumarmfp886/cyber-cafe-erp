"""
Global template context.

Injects ERP metadata into every template render so the branding and
version live in one place (config.settings.base) instead of being
hard-coded across templates.
"""
from django.conf import settings


def erp_context(request):
    return {
        "ERP_APP_NAME": settings.ERP_APP_NAME,
        "ERP_APP_VERSION": settings.ERP_APP_VERSION,
        "ERP_COMPANY_NAME": settings.ERP_COMPANY_NAME,
        "ERP_COMPANY_ADDRESS": settings.ERP_COMPANY_ADDRESS,
    }
