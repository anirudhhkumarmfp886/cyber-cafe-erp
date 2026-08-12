from django.urls import path

from apps.customers.views import customer as customer_views

app_name = "customers"

urlpatterns = [
    path("", customer_views.CustomerListView.as_view(), name="list"),
    path("<uuid:pk>/", customer_views.CustomerDetailView.as_view(), name="detail"),
    path("<uuid:pk>/credit/", customer_views.CustomerCreditDepositView.as_view(), name="credit_deposit"),
    path("<uuid:pk>/edit/", customer_views.CustomerUpdateView.as_view(), name="update"),
    path("<uuid:pk>/deactivate/", customer_views.CustomerDeactivateView.as_view(), name="deactivate"),
]
