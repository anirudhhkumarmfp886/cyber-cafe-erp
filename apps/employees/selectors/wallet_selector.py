"""
WalletSelector — read-only access to wallets and their ledgers.
"""
from django.db.models import Case, F, Sum, When

from apps.employees.models import Wallet, WalletTransactionType
from apps.employees.services.wallet_service import WalletService


class WalletSelector:
    @staticmethod
    def list_with_employees():
        """All wallets with their employee, ordered by employee name."""
        return Wallet.objects.select_related("employee__user").order_by("employee__full_name")

    @staticmethod
    def get_by_id(wallet_id):
        return Wallet.objects.select_related("employee__user").filter(id=wallet_id).first()

    @staticmethod
    def get_by_employee(employee):
        return Wallet.objects.select_related("employee__user").filter(employee=employee).first()

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
