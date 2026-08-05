"""
BankService — the only place bank transactions are created.

Account balances are derived (opening_balance + ledger), never stored.
Deposits credit, withdrawals debit, and inter-account transfers debit one
account and credit another atomically with cross-linked references.
"""
from datetime import date

from django.db import transaction
from django.db.models import Case, F, Sum, When

from apps.common.services.reference_service import ReferenceService
from apps.finance.models import BankAccount, BankTransaction
from apps.finance.models.enums import (
    BankTransactionCategory,
    BankTransactionType,
)


class BankService:
    @staticmethod
    def create_account(
        *,
        account_name: str,
        bank_name: str,
        account_number: str,
        ifsc_code: str = "",
        branch: str = "",
        account_type: str = "CURRENT",
        opening_balance=0,
        by=None,
    ) -> BankAccount:
        if not account_name or not bank_name or not account_number:
            raise ValueError("Account name, bank name and account number are required.")
        if opening_balance < 0:
            raise ValueError("Opening balance cannot be negative.")
        return BankAccount.objects.create(
            account_name=account_name,
            bank_name=bank_name,
            account_number=account_number,
            ifsc_code=ifsc_code,
            branch=branch,
            account_type=account_type,
            opening_balance=opening_balance,
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    def balance_of(account: BankAccount):
        return account.balance

    @staticmethod
    def deposit(
        *,
        account: BankAccount,
        amount,
        category: str = BankTransactionCategory.DEPOSIT,
        party_name: str = "",
        description: str = "",
        entry_date=None,
        by=None,
    ) -> BankTransaction:
        return BankService._apply(
            account=account,
            transaction_type=BankTransactionType.CREDIT,
            amount=amount,
            category=category,
            party_name=party_name,
            description=description,
            entry_date=entry_date,
            by=by,
        )

    @staticmethod
    def withdraw(
        *,
        account: BankAccount,
        amount,
        category: str = BankTransactionCategory.WITHDRAWAL,
        party_name: str = "",
        description: str = "",
        entry_date=None,
        by=None,
    ) -> BankTransaction:
        return BankService._apply(
            account=account,
            transaction_type=BankTransactionType.DEBIT,
            amount=amount,
            category=category,
            party_name=party_name,
            description=description,
            entry_date=entry_date,
            by=by,
        )

    @staticmethod
    @transaction.atomic
    def transfer(
        *,
        from_account: BankAccount,
        to_account: BankAccount,
        amount,
        description: str = "",
        by=None,
        entry_date=None,
    ):
        """Move money between two bank accounts atomically."""
        if from_account.pk == to_account.pk:
            raise ValueError("Cannot transfer to the same account.")

        debit_txn = BankService._apply(
            account=from_account,
            transaction_type=BankTransactionType.DEBIT,
            amount=amount,
            category=BankTransactionCategory.TRANSFER_OUT,
            party_name=to_account.account_name,
            description=description,
            entry_date=entry_date,
            by=by,
        )
        credit_txn = BankService._apply(
            account=to_account,
            transaction_type=BankTransactionType.CREDIT,
            amount=amount,
            category=BankTransactionCategory.TRANSFER_IN,
            party_name=from_account.account_name,
            description=description,
            entry_date=entry_date,
            by=by,
        )
        debit_txn.related_reference = credit_txn.reference_number
        credit_txn.related_reference = debit_txn.reference_number
        debit_txn.save(update_fields=["related_reference", "updated_at"])
        credit_txn.save(update_fields=["related_reference", "updated_at"])
        return debit_txn, credit_txn

    @staticmethod
    def _apply(
        *,
        account: BankAccount,
        transaction_type: str,
        amount,
        category: str,
        party_name: str,
        description: str,
        entry_date,
        by,
    ) -> BankTransaction:
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        account = BankAccount.objects.select_for_update().get(pk=account.pk)
        current = BankService.balance_of(account)

        if transaction_type == BankTransactionType.DEBIT and amount > current:
            raise ValueError("Insufficient bank balance.")

        balance_after = current + amount
        if transaction_type == BankTransactionType.DEBIT:
            balance_after = current - amount

        return BankTransaction.objects.create(
            account=account,
            transaction_type=transaction_type,
            category=category,
            amount=amount,
            balance_after=balance_after,
            reference_number=ReferenceService.next(ReferenceService.BANK),
            party_name=party_name,
            description=description,
            entry_date=entry_date or date.today(),
            created_by=by,
            updated_by=by,
        )
