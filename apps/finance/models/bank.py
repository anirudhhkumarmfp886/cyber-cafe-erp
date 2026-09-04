"""
Bank Ledger — bank accounts and their transactions.

An account carries an immutable opening_balance; the live balance is
opening_balance + SUM(credits) - SUM(debits). Transactions are never edited,
only appended, and each one carries a reference number and the responsible
employee.
"""
from datetime import date

from django.db import models
from django.db.models import Case, F, Sum, When

from apps.common.models import BaseModel, money_field
from apps.finance.models.enums import (
    BankAccountType,
    BankTransactionCategory,
    BankTransactionType,
)


class BankAccount(BaseModel):
    account_name = models.CharField(max_length=150)
    bank_name = models.CharField(max_length=150)
    branch = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, unique=True, db_index=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    account_type = models.CharField(
        max_length=20,
        choices=BankAccountType.choices,
        default=BankAccountType.CURRENT,
    )
    opening_balance = money_field(default=0)
    is_default = models.BooleanField(
        default=False,
        help_text="Default shop bank account for general UPI QR and online payments",
    )

    class Meta:
        ordering = ["account_name"]
        verbose_name = "Bank Account"
        verbose_name_plural = "Bank Accounts"

    def __str__(self):
        return f"{self.account_name} ({self.bank_name})"

    @property
    def balance(self):
        """Derived balance = opening balance + credits - debits."""
        net = self.transactions.aggregate(
            net=Sum(
                Case(
                    When(transaction_type=BankTransactionType.CREDIT, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return (net or 0) + self.opening_balance


class BankTransaction(BaseModel):
    account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=BankTransactionType.choices,
        db_index=True,
    )
    category = models.CharField(max_length=30, choices=BankTransactionCategory.choices)
    amount = money_field()
    balance_after = money_field(editable=False)
    reference_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    related_reference = models.CharField(
        max_length=30, blank=True, editable=False,
        help_text="Reference of the paired transaction (e.g. bank-to-bank transfer).",
    )
    party_name = models.CharField(
        max_length=150, blank=True,
        help_text="Counterparty: who deposited or was paid.",
    )
    description = models.TextField(blank=True)
    entry_date = models.DateField(default=date.today, db_index=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Bank Transaction"
        verbose_name_plural = "Bank Transactions"
        indexes = [
            models.Index(fields=["account", "entry_date"]),
        ]

    def __str__(self):
        return f"{self.reference_number} {self.transaction_type} {self.amount}"

    @property
    def is_credit(self) -> bool:
        return self.transaction_type == BankTransactionType.CREDIT
