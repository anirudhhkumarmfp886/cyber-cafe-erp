"""Public and shared pages (dashboard, home, etc.)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.billing.selectors.invoice_selector import InvoiceSelector
from apps.customers.selectors.customer_selector import CustomerSelector
from apps.employees.selectors.employee_selector import EmployeeSelector
from apps.employees.selectors.wallet_selector import WalletSelector
from apps.employees.selectors.worklog_selector import WorkLogSelector
from apps.finance.selectors.bank_selector import BankSelector
from apps.finance.selectors.cashbook_selector import CashBookSelector
from apps.reports.services.report_service import ReportService
from apps.inventory.selectors.inventory_selector import InventorySelector
from apps.services.selectors.service_selector import ServiceSelector


@login_required
def dashboard(request):
    """Landing dashboard after login. Shows billing + finance at a glance."""
    today = timezone.localdate()
    context = {
        "page_title": "Dashboard",
        "stats": {
            "total_employees": EmployeeSelector.count_active(),
            "active_employees": EmployeeSelector.count_active(),
            "total_users": EmployeeSelector.count_users(),
            "total_customers": CustomerSelector.count_active(),
            "total_services": ServiceSelector.count_active(),
            "pending_worklogs": WorkLogSelector.pending_count(),
            "pending_invoices": InvoiceSelector.pending_count(),
            "outstanding_total": InvoiceSelector.pending_total(),
            "today_billing": InvoiceSelector.today_billing_total(),
        },
        "finance": {
            "wallet_balance": WalletSelector.total_wallet_balance(),
            "cashbook_balance": CashBookSelector.balance(),
            "bank_balance": BankSelector.total_balance(),
            "today_income": ReportService.income_total(from_date=today, to_date=today),
        },
        "top_services": InvoiceSelector.top_services(days=30, limit=5),
        "inventory": {
            "total_items": InventorySelector.count_active(),
            "low_stock_count": InventorySelector.count_low_stock(),
            "stock_value": InventorySelector.total_stock_value(),
        },
    }
    return render(request, "pages/dashboard.html", context)
