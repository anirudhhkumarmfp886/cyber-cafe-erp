"""
WalletSelector — read-only access to wallets and their ledgers.
"""
from django.db.models import Case, F, Sum, When

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
            rows.append(
                {
                    "employee": employee,
                    "cash_wallet": cash,
                    "cash_balance": WalletService.balance_of(cash),
                    "online_wallet": online,
                    "online_balance": WalletService.balance_of(online),
                    "total_balance": WalletService.balance_of(cash) + WalletService.balance_of(online),
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
    def balance_of(wallet):
        return WalletService.balance_of(wallet)

    @staticmethod
    def total_wallet_balance():
        """Sum of every wallet's current balance across all employees."""
        total = Wallet.objects.aggregate(
            net=Sum(
                Case(
                    When(transactions__transaction_type=WalletTransactionType.CREDIT, then=F("transactions__amount")),
                    default=-F("transactions__amount"),
                )
            )
        )["net"]
        return total or 0
