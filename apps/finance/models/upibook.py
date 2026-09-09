"""
UPI Book — the day-to-day digital/UPI operational float and inflow/outflow register of the cafe.

Every UPI movement into or out of the shop operational pool is recorded here.
Running UPI float balance is always derived from the ledger (INCOME minus EXPENSE).
Each entry carries a unique reference number (UB-XXXXXX), linked bank account,
responsible staff/party, and category.
"""
from datetime import date

from django.db import models

from apps.common.models import BaseModel, money_field
from apps.employees.models import Employee
from apps.finance.models.bank import BankAccount
from apps.finance.models.enums import CashEntryCategory, CashEntryType


class UPIBookEntry(BaseModel):
    entry_date = models.DateField(default=date.today, db_index=True)
    entry_type = models.CharField(max_length=10, choices=CashEntryType.choices, db_index=True)
    category = models.CharField(max_length=30, choices=CashEntryCategory.choices)
    amount = money_field()
    reference_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upi_entries",
        help_text="Linked bank account for float funding, customer deposits, or sweeps.",
    )
    party_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Customer / Vendor / UPI App / Staff.",
    )
    description = models.TextField(blank=True)
    staff = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upi_entries",
        help_text="Responsible staff member if entry is assigned to or handled by staff.",
    )

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "UPI Book Entry"
        verbose_name_plural = "UPI Book Entries"
        indexes = [
            models.Index(fields=["entry_date", "entry_type"]),
            models.Index(fields=["staff", "entry_date"]),
        ]
        permissions = [
            ("withdraw_shop_upi", "Can withdraw / sweep UPI float from the shop UPI book"),
        ]

    def __str__(self):
        return f"{self.reference_number} {self.entry_type} {self.amount}"

    @property
    def is_income(self) -> bool:
        return self.entry_type == CashEntryType.INCOME
