"""
WalletService — the only place wallet money moves.

Rules enforced here (and nowhere else in the web layer):
  * amount must be strictly positive
  * a debit can never take a wallet below zero
  * every move mints a unique reference number and a balance_after snapshot
  * credit + debit of a wallet-to-wallet transfer happen atomically

Balance is always derived from the transaction ledger; it is never stored
as a mutable field.
"""
from datetime import date

from django.db import transaction
from django.db.models import Case, F, Sum, When

from apps.common.services.reference_service import ReferenceService
from apps.employees.models import (
    Employee,
    Wallet,
    WalletTransaction,
    WalletTransactionCategory,
    WalletTransactionType,
)


class WalletService:
    @staticmethod
    def get_or_create_wallet(employee: Employee) -> Wallet:
        wallet, _ = Wallet.objects.get_or_create(employee=employee)
        return wallet

    @staticmethod
    def balance_of(wallet: Wallet):
        total = wallet.transactions.aggregate(
            net=Sum(
                Case(
                    When(transaction_type=WalletTransactionType.CREDIT, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def balance_of_employee(employee: Employee):
        return WalletService.balance_of(WalletService.get_or_create_wallet(employee))

    @staticmethod
    @transaction.atomic
    def credit(
        *,
        wallet: Wallet,
        amount,
        category: str = WalletTransactionCategory.CASH_TOPUP,
        description: str = "",
        source: str = "",
        destination: str = "",
        by=None,
        entry_date=None,
    ) -> WalletTransaction:
        return WalletService._apply(
            wallet=wallet,
            transaction_type=WalletTransactionType.CREDIT,
            amount=amount,
            category=category,
            description=description,
            source=source,
            destination=destination,
            by=by,
            entry_date=entry_date,
        )

    @staticmethod
    @transaction.atomic
    def debit(
        *,
        wallet: Wallet,
        amount,
        category: str = WalletTransactionCategory.CASH_WITHDRAWAL,
        description: str = "",
        source: str = "",
        destination: str = "",
        by=None,
        entry_date=None,
    ) -> WalletTransaction:
        return WalletService._apply(
            wallet=wallet,
            transaction_type=WalletTransactionType.DEBIT,
            amount=amount,
            category=category,
            description=description,
            source=source,
            destination=destination,
            by=by,
            entry_date=entry_date,
        )

    @staticmethod
    @transaction.atomic
    def transfer(
        *,
        from_employee: Employee,
        to_employee: Employee,
        amount,
        description: str = "",
        by=None,
        entry_date=None,
    ):
        """Move money between two employee wallets atomically.

        Returns (debit_transaction, credit_transaction) with their reference
        numbers cross-linked for the audit trail.
        """
        if from_employee.pk == to_employee.pk:
            raise ValueError("Cannot transfer to the same wallet.")

        source_wallet = WalletService.get_or_create_wallet(from_employee)
        target_wallet = WalletService.get_or_create_wallet(to_employee)
        entry_date = entry_date or date.today()

        debit_txn = WalletService._apply(
            wallet=source_wallet,
            transaction_type=WalletTransactionType.DEBIT,
            amount=amount,
            category=WalletTransactionCategory.TRANSFER_OUT,
            description=description,
            source=f"{from_employee.full_name} wallet",
            destination=f"{to_employee.full_name} wallet",
            by=by,
            entry_date=entry_date,
        )
        credit_txn = WalletService._apply(
            wallet=target_wallet,
            transaction_type=WalletTransactionType.CREDIT,
            amount=amount,
            category=WalletTransactionCategory.TRANSFER_IN,
            description=description,
            source=f"{from_employee.full_name} wallet",
            destination=f"{to_employee.full_name} wallet",
            by=by,
            entry_date=entry_date,
        )
        # Cross-link both sides of the transfer.
        debit_txn.related_reference = credit_txn.reference_number
        credit_txn.related_reference = debit_txn.reference_number
        debit_txn.save(update_fields=["related_reference", "updated_at"])
        credit_txn.save(update_fields=["related_reference", "updated_at"])
        return debit_txn, credit_txn

    @staticmethod
    def _apply(
        *,
        wallet: Wallet,
        transaction_type: str,
        amount,
        category: str,
        description: str,
        source: str,
        destination: str,
        by,
        entry_date,
    ) -> WalletTransaction:
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        # Serialize concurrent writes on the same wallet.
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        current = WalletService.balance_of(wallet)

        if transaction_type == WalletTransactionType.DEBIT and amount > current:
            raise ValueError("Insufficient wallet balance.")

        balance_after = current + amount
        if transaction_type == WalletTransactionType.DEBIT:
            balance_after = current - amount

        return WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            category=category,
            amount=amount,
            balance_after=balance_after,
            reference_number=ReferenceService.next(ReferenceService.WALLET),
            source=source,
            destination=destination,
            description=description,
            entry_date=entry_date or date.today(),
            created_by=by,
            updated_by=by,
        )
