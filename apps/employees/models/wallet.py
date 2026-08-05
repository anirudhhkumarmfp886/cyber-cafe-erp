"""
Wallet Engine — per-employee staff wallet.

Accounting principle: the wallet itself stores no balance. The running
balance is always computed from the WalletTransaction ledger (SUM of
credits minus debits). Each transaction carries a snapshot (balance_after)
purely for audit/history, and a unique reference number.

Money flow (Sprint 2 scope):

    Owner cash  --top-up-->  Employee wallet  --withdrawal-->  Cash
                             wallet --transfer-->  another wallet

Responsible employee = transaction.created_by (auto-filled by middleware).
"""
from datetime import date

from django.db import models
from django.db.models import Case, F, Sum, When

from apps.common.models import BaseModel, money_field
from apps.employees.models import Employee


class WalletTransactionType(models.TextChoices):
    CREDIT = "CREDIT", "Credit"
    DEBIT = "DEBIT", "Debit"


class WalletTransactionCategory(models.TextChoices):
    CASH_TOPUP = "CASH_TOPUP", "Cash Top-up"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
    SALARY = "SALARY", "Salary Payment"
    ADVANCE = "ADVANCE", "Advance"
    BONUS = "BONUS", "Bonus"
    PENALTY = "PENALTY", "Penalty"
    TRANSFER_IN = "TRANSFER_IN", "Transfer In"
    TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
    PAYMENT_COLLECTED = "PAYMENT_COLLECTED", "Payment Collected"
    EXPENSE = "EXPENSE", "Expense"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class Wallet(BaseModel):
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name="wallet",
        help_text="The employee this wallet belongs to.",
    )

    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self):
        return f"Wallet: {self.employee.full_name}"

    @property
    def balance(self):
        """Current balance derived from the ledger, never stored."""
        total = self.transactions.aggregate(
            net=Sum(
                Case(
                    When(transaction_type=WalletTransactionType.CREDIT, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0


class WalletTransaction(BaseModel):
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=WalletTransactionType.choices,
        db_index=True,
    )
    category = models.CharField(max_length=30, choices=WalletTransactionCategory.choices)
    amount = money_field()
    balance_after = money_field(editable=False)
    reference_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    related_reference = models.CharField(
        max_length=30, blank=True, editable=False,
        help_text="Reference of the paired transaction (e.g. wallet-to-wallet transfer).",
    )
    source = models.CharField(max_length=150, blank=True, help_text="Where the money came from.")
    destination = models.CharField(max_length=150, blank=True, help_text="Where the money went.")
    description = models.TextField(blank=True)
    entry_date = models.DateField(default=date.today, db_index=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Wallet Transaction"
        verbose_name_plural = "Wallet Transactions"
        indexes = [
            models.Index(fields=["wallet", "entry_date"]),
        ]

    def __str__(self):
        return f"{self.reference_number} {self.transaction_type} {self.amount}"

    @property
    def is_credit(self) -> bool:
        return self.transaction_type == WalletTransactionType.CREDIT
