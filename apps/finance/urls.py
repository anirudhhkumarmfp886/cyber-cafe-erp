from django.urls import path

from apps.finance.views import bank as bank_views
from apps.finance.views import cashbook as cashbook_views
from apps.finance.views import upibook as upibook_views

app_name = "finance"

urlpatterns = [
    path("cashbook/", cashbook_views.CashBookListView.as_view(), name="cashbook_list"),
    path("cashbook/owner-cash/", cashbook_views.OwnerCashView.as_view(), name="cashbook_owner_cash"),
    path("cashbook/bulk-delete/", cashbook_views.CashBookBulkDeleteView.as_view(), name="cashbook_bulk_delete"),
    path("cashbook/<uuid:pk>/delete/", cashbook_views.CashBookDeleteView.as_view(), name="cashbook_delete"),
    path("upibook/", upibook_views.UPIBookListView.as_view(), name="upibook_list"),
    path("upibook/action/", upibook_views.OwnerUPIActionView.as_view(), name="upibook_action"),
    path("upibook/bulk-delete/", upibook_views.UPIBookBulkDeleteView.as_view(), name="upibook_bulk_delete"),
    path("upibook/<uuid:pk>/delete/", upibook_views.UPIBookDeleteView.as_view(), name="upibook_delete"),
    path("bank/", bank_views.BankAccountListView.as_view(), name="bank_list"),
    path("bank/<uuid:pk>/", bank_views.BankAccountDetailView.as_view(), name="bank_detail"),
    path("bank/<uuid:pk>/set-default/", bank_views.SetDefaultBankAccountView.as_view(), name="bank_set_default"),
]
