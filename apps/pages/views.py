"""Public and shared pages (dashboard, home, etc.)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.employees.selectors.employee_selector import EmployeeSelector
from apps.employees.selectors.wallet_selector import WalletSelector
from apps.finance.selectors.bank_selector import BankSelector
from apps.finance.selectors.cashbook_selector import CashBookSelector


@login_required
def dashboard(request):
    """Landing dashboard after login. Billing analytics arrive in Sprint 4."""
    today = timezone.localdate()
    context = {
        "page_title": "Dashboard",
        "stats": {
            "total_employees": EmployeeSelector.count_active(),
            "active_employees": EmployeeSelector.count_active(),
            "total_users": EmployeeSelector.count_users(),
        },
        "finance": {
            "wallet_balance": WalletSelector.total_wallet_balance(),
            "cashbook_balance": CashBookSelector.balance(),
            "bank_balance": BankSelector.total_balance(),
            "today_income": CashBookSelector.income_total(from_date=today, to_date=today),
        },
    }
    return render(request, "pages/dashboard.html", context)
