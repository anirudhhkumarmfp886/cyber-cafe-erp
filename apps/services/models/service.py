"""
Service catalog — billable services offered by the cafe.

A service is a catalogue item (game hour, internet package, print page,
recharge, ...) with a current selling price. Price changes are append-only
in ServicePriceHistory so the ledger can always explain what was charged
at any point in time.
"""
from apps.common.models import BaseModel, money_field
from django.db import models


class ServiceCategory(models.TextChoices):
    GAMES = "GAMES", "Games"
    INTERNET = "INTERNET", "Internet"
    PRINTING = "PRINTING", "Printing"
    RECHARGE = "RECHARGE", "Recharge"
    SNACKS = "SNACKS", "Snacks"
    OTHER = "OTHER", "Other"


class Service(BaseModel):
    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(
        max_length=30,
        choices=ServiceCategory.choices,
        default=ServiceCategory.OTHER,
        blank=True,
        db_index=True,
    )
    unit = models.CharField(max_length=50, blank=True, help_text="Billing unit, e.g. 'per hour', 'per page'.")
    price = money_field()
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Service"
        verbose_name_plural = "Services"
        indexes = [
            models.Index(fields=["category", "name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.price})"


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
