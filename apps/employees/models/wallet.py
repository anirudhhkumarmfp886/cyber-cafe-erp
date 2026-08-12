"""
Wallet Engine — per-employee staff wallets.

Each staff member has TWO wallets (Phase: 2-wallet model):

    * CASH wallet   — cash float the staff handles at the counter
    * ONLINE wallet — UPI / online money the staff collects on behalf of
                      the shop

Accounting principle: a wallet stores no balance. The running balance is
always computed from the WalletTransaction ledger (SUM of credits minus
debits). Each transaction carries a snapshot (balance_after) purely for
audit/history, and a unique reference number.

Money flow (Sprint 2 scope + 2-wallet extension):

    Owner cash  --top-up-->  Employee CASH wallet
    Owner bank  --top-up-->  Employee ONLINE wallet
    Sales by staff --credit-->  CASH / ONLINE wallet
    Cash given to customer --debit-->  CASH wallet

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


class WalletType(models.TextChoices):
    CASH = "CASH", "Cash"
    ONLINE = "ONLINE", "Online / UPI"


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
    CASH_GIVEN = "CASH_GIVEN", "Cash Given to Customer"
    PAYOUT = "PAYOUT", "Customer Payout / Transfer"
    EXPENSE = "EXPENSE", "Expense"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class Wallet(BaseModel):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="wallets",
        help_text="The employee this wallet belongs to.",
    )
    wallet_type = models.CharField(
        max_length=10,
        choices=WalletType.choices,
        default=WalletType.CASH,
        db_index=True,
        help_text="CASH float or ONLINE / UPI collections wallet.",
    )

    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "wallet_type"],
                name="unique_wallet_per_employee_and_type",
            ),
        ]

    def __str__(self):
        return f"{self.get_wallet_type_display()} Wallet: {self.employee.full_name}"

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
