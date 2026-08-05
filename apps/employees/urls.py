from django.urls import path

from apps.employees.views import employee as employee_views
from apps.employees.views import wallet as wallet_views

app_name = "employees"

urlpatterns = [
    path("", employee_views.EmployeeListView.as_view(), name="list"),
    path("add/", employee_views.EmployeeCreateView.as_view(), name="create"),
    path("wallets/", wallet_views.WalletListView.as_view(), name="wallet_list"),
    path("wallets/<uuid:pk>/", wallet_views.WalletDetailView.as_view(), name="wallet_detail"),
    path("<uuid:pk>/", employee_views.EmployeeDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", employee_views.EmployeeUpdateView.as_view(), name="update"),
    path("<uuid:pk>/deactivate/", employee_views.EmployeeDeactivateView.as_view(), name="deactivate"),
]
