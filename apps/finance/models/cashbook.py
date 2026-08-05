"""
Cash Book — the day-to-day cash inflow/outflow register of the cafe.

Every cash movement in or out of the business is recorded here. The running
cash balance is always derived from the ledger (INCOME total minus EXPENSE
total); never stored. Each entry carries a unique reference number, the
responsible employee (created_by) and the payment mode.
"""
from datetime import date

from django.db import models

from apps.common.models import BaseModel, money_field
from apps.finance.models.enums import CashEntryCategory, CashEntryType, PaymentMode


class CashBookEntry(BaseModel):
    entry_date = models.DateField(default=date.today, db_index=True)
    entry_type = models.CharField(max_length=10, choices=CashEntryType.choices, db_index=True)
    category = models.CharField(max_length=30, choices=CashEntryCategory.choices)
    payment_mode = models.CharField(
        max_length=20,
        choices=PaymentMode.choices,
        default=PaymentMode.CASH,
        db_index=True,
    )
    amount = money_field()
    reference_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    party_name = models.CharField(
        max_length=150, blank=True,
        help_text="Who we received from / paid to (customer, vendor, party).",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Cash Book Entry"
        verbose_name_plural = "Cash Book Entries"
        indexes = [
            models.Index(fields=["entry_date", "entry_type"]),
        ]

    def __str__(self):
        return f"{self.reference_number} {self.entry_type} {self.amount}"

    @property
    def is_income(self) -> bool:
        return self.entry_type == CashEntryType.INCOME
