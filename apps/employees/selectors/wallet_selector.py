"""
WalletSelector — read-only access to wallets and their ledgers.
"""
from django.db.models import Case, F, Q, Sum, When

from apps.employees.models import Wallet, WalletTransactionType, WalletType
from apps.employees.services.wallet_service import WalletService


class WalletSelector:
    @staticmethod
    def list_with_employees():
        """All wallets with their employee, ordered by employee name."""
        return Wallet.objects.select_related("employee__user").order_by("employee__full_name", "wallet_type")

    @staticmethod
    def list_employees_with_wallets():
        """Active employees each carrying their CASH + ONLINE wallets."""
        from apps.employees.models import Employee, EmploymentStatus

        employees = Employee.objects.filter(status=EmploymentStatus.ACTIVE).order_by("full_name")
        rows = []
        for employee in employees:
            cash = WalletService.get_or_create_wallet(employee, WalletType.CASH)
            online = WalletService.get_or_create_wallet(employee, WalletType.ONLINE)
            from apps.employees.selectors.employee_selector import EmployeeSelector
            stats = EmployeeSelector.get_income_stats(employee)
            rows.append(
                {
                    "employee": employee,
                    "cash_wallet": cash,
                    "cash_balance": WalletService.balance_of(cash),
                    "online_wallet": online,
                    "online_balance": WalletService.balance_of(online),
                    "total_balance": WalletService.balance_of(cash) + WalletService.balance_of(online),
                    "today_income": stats["today_income"],
                    "today_bills_count": stats["today_bills_count"],
                    "month_income": stats["month_income"],
                }
            )
        return rows

    @staticmethod
    def get_by_id(wallet_id):
        return Wallet.objects.select_related("employee__user").filter(id=wallet_id).first()

    @staticmethod
    def get_by_employee(employee, wallet_type: str = WalletType.CASH):
        return Wallet.objects.select_related("employee__user").filter(
            employee=employee, wallet_type=wallet_type
        ).first()

    @staticmethod
    def transactions(wallet, limit: int = 100):
        return wallet.transactions.select_related("created_by").order_by("-entry_date", "-created_at")[:limit]

    @staticmethod
    def filter_transactions(wallet, filters: dict | None = None):
        filters = filters or {}
        qs = wallet.transactions.select_related("created_by").order_by("-entry_date", "-created_at")
        if filters.get("from_date"):
            qs = qs.filter(entry_date__gte=filters["from_date"])
        if filters.get("to_date"):
            qs = qs.filter(entry_date__lte=filters["to_date"])
        if filters.get("category"):
            qs = qs.filter(category=filters["category"])
        if filters.get("transaction_type"):
            qs = qs.filter(transaction_type=filters["transaction_type"])
        if filters.get("q"):
            q = filters["q"]
            qs = qs.filter(
                Q(reference_number__icontains=q)
                | Q(source__icontains=q)
                | Q(destination__icontains=q)
                | Q(description__icontains=q)
            )
        return qs

    @staticmethod
    def balance_of(wallet):
        return WalletService.balance_of(wallet)

    @staticmethod
    def total_wallet_balance() -> float:
        """Sum of all wallet balances across all active employees."""
        rows = WalletSelector.list_employees_with_wallets()
        return sum(r["total_balance"] for r in rows)

    @staticmethod
    def total_staff_float(wallet_type: str = WalletType.ONLINE, on_date=None) -> float:
        """Sum of all active staff float balances for a wallet type (CASH or ONLINE)."""
        from apps.employees.models import Employee, EmploymentStatus

        employees = Employee.objects.filter(status=EmploymentStatus.ACTIVE)
        total = 0
        for emp in employees:
            wallet = WalletService.get_or_create_wallet(emp, wallet_type)
            bal = WalletService.balance_of_on(wallet, on_date) if on_date else WalletService.balance_of(wallet)
            total += bal
        return total

    @staticmethod
    def staff_float_breakdown(wallet_type: str = WalletType.ONLINE, on_date=None) -> list:
        """List of active staff with their float balance for a wallet type."""
        from apps.employees.models import Employee, EmploymentStatus

        employees = Employee.objects.filter(status=EmploymentStatus.ACTIVE).order_by("full_name")
        breakdown = []
        for emp in employees:
            wallet = WalletService.get_or_create_wallet(emp, wallet_type)
            bal = WalletService.balance_of_on(wallet, on_date) if on_date else WalletService.balance_of(wallet)
            if bal != 0:
                breakdown.append(
                    {
                        "employee": emp,
                        "wallet": wallet,
                        "balance": bal,
                    }
                )
        return breakdown

