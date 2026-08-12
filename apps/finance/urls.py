from django.urls import path

from apps.finance.views import bank as bank_views
from apps.finance.views import cashbook as cashbook_views

app_name = "finance"

urlpatterns = [
    path("cashbook/", cashbook_views.CashBookListView.as_view(), name="cashbook_list"),
    path("cashbook/owner-cash/", cashbook_views.OwnerCashView.as_view(), name="cashbook_owner_cash"),
    path("cashbook/<uuid:pk>/delete/", cashbook_views.CashBookDeleteView.as_view(), name="cashbook_delete"),
    path("bank/", bank_views.BankAccountListView.as_view(), name="bank_list"),
    path("bank/<uuid:pk>/", bank_views.BankAccountDetailView.as_view(), name="bank_detail"),
]
