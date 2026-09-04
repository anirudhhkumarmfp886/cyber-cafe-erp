"""
Service catalog — billable services offered by the cafe.

A service is a catalogue item (game hour, internet package, print page,
recharge, ...) with a current selling price. Price changes are append-only
in ServicePriceHistory so the ledger can always explain what was charged
at any point in time.

Categories are free-form (owner-created) instead of a fixed choice list,
so the catalog can grow beyond the initial defaults. A service may also
carry ``ServiceCustomField`` definitions — dynamic inputs captured on the
bill for that service (e.g. a cash-withdrawal service records the amount
given, the commission percentage, and which bank account the customer
transferred into). Bank-transfer fields trigger an automatic bank deposit
when the service is billed.

How the amount is charged is formula-driven. A service with no formulas is
priced ``qty × price`` like a plain sale. An owner may instead supply a
``total_formula`` (what the customer is charged) and an ``income_formula``
(what the shop actually keeps) built from the service's field variables —
see ``apps.common.services.formula``. A ``passthrough_type`` other than
``NONE`` marks that the difference between the two is money moving on the
customer's behalf (cash handed out, online transfer), not shop income.
"""
from apps.common.models import BaseModel, money_field
from apps.common.services.formula import ServicePassThroughType
from django.db import models


class Category(BaseModel):
    """Free-form service category (Games, Internet, Printing, ...)."""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"

    def __str__(self):
        return self.name


class CustomFieldType(models.TextChoices):
    TEXT = "TEXT", "Text"
    NUMBER = "NUMBER", "Number (amount)"
    PERCENT = "PERCENT", "Percentage"
    DATE = "DATE", "Date"
    BANK_ACCOUNT = "BANK_ACCOUNT", "Bank Account"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer (auto-deposit)"


class Service(BaseModel):
    name = models.CharField(max_length=150, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="services",
        db_index=True,
        help_text="Optional; defaults to the 'Other' category.",
    )
    unit = models.CharField(max_length=50, blank=True, help_text="Billing unit, e.g. 'per hour', 'per page'.")
    price = money_field()
    description = models.TextField(blank=True)
    passthrough_type = models.CharField(
        max_length=20,
        choices=ServicePassThroughType.choices,
        default=ServicePassThroughType.NONE,
        help_text="How pass-through money leaves the shop when this service is billed.",
    )
    total_formula = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional formula for what the customer is charged. Uses field variables, qty, price. "
        "Leave blank for qty × price.",
    )
    income_formula = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional formula for what the shop keeps. Leave blank to keep the whole line amount.",
    )
    default_bank_account = models.ForeignKey(
        "finance.BankAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services",
        help_text="Default/dedicated bank account for this service (e.g. AEPS CBI account)",
    )

    class Meta:
        ordering = ["category__name", "name"]
        verbose_name = "Service"
        verbose_name_plural = "Services"
        indexes = [
            models.Index(fields=["category", "name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.price})"

    @property
    def category_name(self) -> str:
        return self.category.name if self.category else "Other"


class ServiceCustomField(BaseModel):
    """Dynamic input captured on the bill when a service is billed.

    Field visibility is role-based: the owner lists the role codes allowed
    to see and fill a field in ``roles`` (comma-separated). An empty list
    means every billing-capable staff member can use it. Bank-transfer
    fields (``BANK_TRANSFER`` + ``BANK_ACCOUNT``) trigger a real bank
    deposit into the selected account when the service is billed.
    """

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="custom_fields",
    )
    label = models.CharField(max_length=100)
    variable_name = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Machine name used inside service formulas, e.g. 'cash_amount'. "
        "Auto-generated from the label when left blank.",
    )
    field_type = models.CharField(
        max_length=20,
        choices=CustomFieldType.choices,
        default=CustomFieldType.TEXT,
        db_index=True,
    )
    required = models.BooleanField(default=False)
    help_text = models.CharField(max_length=200, blank=True)
    roles = models.CharField(
        max_length=200,
        blank=True,
        help_text="Comma-separated role codes allowed to fill this field. Leave blank for all billing staff.",
    )
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordering", "created_at"]
        verbose_name = "Service Custom Field"
        verbose_name_plural = "Service Custom Fields"
        indexes = [
            models.Index(fields=["service", "field_type"]),
        ]

    def __str__(self):
        return f"{self.service.name} - {self.label}"

    def role_list(self) -> list[str]:
        return [code.strip() for code in self.roles.split(",") if code.strip()]


class ServicePriceHistory(BaseModel):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="price_history")
    price = money_field()
    effective_from = models.DateField(db_index=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-effective_from", "-created_at"]
        verbose_name = "Service Price History"
        verbose_name_plural = "Service Price Histories"
        indexes = [
            models.Index(fields=["service", "effective_from"]),
        ]

    def __str__(self):
        return f"{self.service.name} @ {self.price} from {self.effective_from}"
