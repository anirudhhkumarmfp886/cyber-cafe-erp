"""Root URL configuration for AK Nazar Cyber Cafe ERP."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("employees/", include("apps.employees.urls")),
    path("finance/", include("apps.finance.urls")),
    path("customers/", include("apps.customers.urls")),
    path("services/", include("apps.services.urls")),
    path("billing/", include("apps.billing.urls")),
    path("reports/", include("apps.reports.urls")),
    path("", include("apps.pages.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
