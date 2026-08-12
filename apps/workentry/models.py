"""
Work Entry — the counter page where staff record a piece of work.

A single work entry captures one service (with an optional page quantity)
plus up to three money "legs" the shop executes on the customer's behalf:

    charged_amount       -> the shop's income (SALES). This is the ONLY
                            figure the P&L treats as income; the total the
                            customer pays also covers the legs below.
    transfer_to_customer -> money moved from the staff ONLINE wallet into
                            the customer's own account (a payout).
    transfer_on_behalf   -> money paid out of the staff wallet to a third
                            party on the customer's behalf (a payout).
    cash_withdrawal      -> cash handed to the customer from the staff
                            CASH wallet (like E-Sathi).

The customer pays ``charged + transfers + cash_withdrawal`` through the
``payment_mode``. ``income`` always equals ``charged_amount`` — the legs are
pass-through. A DRAFT entry is generated on the counter page; the "Billed"
step opens an editable bill, and "Save Bill" (``WorkEntryService.finalize``)
books every ledger atomically and marks the entry SAVED.
"""
from datetime import date

from django.db import models

from apps.common.models import BaseModel, money_field
from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.finance.models import BankAccount
from apps.services.models import Service


class WorkEntryStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SAVED = "SAVED", "Saved"


class WorkPaymentMode(models.TextChoices):
    CASH = "CASH", "Cash"
    UPI = "UPI", "UPI"
    CARD = "CARD", "Card"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
    CUSTOMER_CREDIT = "CUSTOMER_CREDIT", "Customer Credit"


#: How the part of a CUSTOMER_CREDIT bill that the credit does not cover is paid.
CREDIT_REST_MODES = (
    ("CASH", "Cash"),
    ("UPI", "UPI"),
    ("CARD", "Card"),
    ("BANK_TRANSFER", "Bank Transfer"),
)


class WorkEntry(BaseModel):
    reference_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="work_entries",
        help_text="Staff member who did the work (auto-filled from the login).",
    )
    entry_date = models.DateField(default=date.today, db_index=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_entries",
        help_text="Optional; walk-in work may leave this blank.",
    )
    customer_name = models.CharField(max_length=150, blank=True, db_index=True)
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="work_entries",
        help_text="Work type / service from the catalog.",
    )
    page_quantity = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    charged_amount = money_field(default=0)

    payment_mode = models.CharField(
        max_length=20,
        choices=WorkPaymentMode.choices,
        default=WorkPaymentMode.CASH,
        db_index=True,
    )
    credit_rest_mode = models.CharField(
        max_length=20,
        choices=CREDIT_REST_MODES,
        blank=True,
        help_text="How the unpaid rest of a customer-credit bill is collected.",
    )
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Shop bank / UPI account that receives online payments.",
    )

    transfer_to_customer = money_field(default=0)
    transfer_on_behalf = money_field(default=0)
    cash_withdrawal = money_field(default=0)

    #: Snapshots fixed at finalize time (editable=False).
    credit_used = money_field(default=0, editable=False)
    total = money_field(default=0, editable=False)
    income = money_field(default=0, editable=False)

    status = models.CharField(
        max_length=10,
        choices=WorkEntryStatus.choices,
        default=WorkEntryStatus.DRAFT,
        db_index=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Work Entry"
        verbose_name_plural = "Work Entries"
        indexes = [
            models.Index(fields=["employee", "entry_date"]),
            models.Index(fields=["status", "entry_date"]),
        ]

    def __str__(self):
        return f"{self.reference_number} {self.entry_date} {self.service.name}"

    @property
    def customer_display(self) -> str:
        if self.customer:
            return self.customer.full_name
        return self.customer_name or "Walk-in Customer"

    @property
    def leg_total(self):
        """The pass-through legs: transfers + cash withdrawal."""
        return self.transfer_to_customer + self.transfer_on_behalf + self.cash_withdrawal

    @property
    def total_amount(self):
        """What the customer pays = income + pass-through legs."""
        return self.charged_amount + self.leg_total
