"""BankSelector — read-only access to bank accounts and transactions."""
from django.db.models import Case, F, Sum, When

from apps.finance.models import BankAccount
from apps.finance.models.enums import BankTransactionType


class BankSelector:
    @staticmethod
    def list_accounts():
        return BankAccount.objects.order_by("account_name")

    @staticmethod
    def get_by_id(account_id):
        return BankAccount.objects.filter(id=account_id).first()

    @staticmethod
    def transactions(account, limit: int = 150):
        return account.transactions.order_by("-entry_date", "-created_at")[:limit]

    @staticmethod
    def total_balance() -> float:
        """Sum of all account balances (opening + ledger)."""
        total = 0
        for account in BankAccount.objects.all():
            net = account.transactions.aggregate(
                net=Sum(
                    Case(
                        When(transaction_type=BankTransactionType.CREDIT, then=F("amount")),
                        default=-F("amount"),
                    )
                )
            )["net"]
            total += (net or 0) + account.opening_balance
        return total
