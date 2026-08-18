from django.urls import path

from apps.billing.views import invoice as invoice_views

app_name = "billing"

urlpatterns = [
    path("", invoice_views.InvoiceListView.as_view(), name="list"),
    path("<uuid:pk>/", invoice_views.InvoiceDetailView.as_view(), name="detail"),
    path("<uuid:pk>/settle/", invoice_views.InvoiceSettleView.as_view(), name="settle"),
    path("<uuid:pk>/delete/", invoice_views.InvoiceDeleteView.as_view(), name="delete"),
]
