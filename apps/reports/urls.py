from django.urls import path

from apps.reports.views import report_views

app_name = "reports"

urlpatterns = [
    path("", report_views.ReportIndexView.as_view(), name="index"),
    path("profit-loss/", report_views.ProfitLossView.as_view(), name="profit_loss"),
    path("bank-statement/", report_views.BankStatementView.as_view(), name="bank_statement"),
    path("customer-ledger/", report_views.CustomerLedgerView.as_view(), name="customer_ledger"),
    path("wallet-statement/", report_views.WalletStatementView.as_view(), name="wallet_statement"),
    path("salary-summary/", report_views.SalarySummaryView.as_view(), name="salary_summary"),
    path("analytics/", report_views.AnalyticsView.as_view(), name="analytics"),
]
