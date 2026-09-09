"""Customer credit ledger & limit change audit log."""
from django.conf import settings
from django.db import models

from apps.common.models import BaseModel, money_field
from apps.customers.models.customer import Customer


class CreditLogType(models.TextChoices):
    LIMIT_CHANGE = "LIMIT_CHANGE", "Credit Limit Change"
    PREPAID_DEPOSIT = "PREPAID_DEPOSIT", "Prepaid Advance Deposit"
    PREPAID_USAGE = "PREPAID_USAGE", "Prepaid Balance Used"
    PREPAID_REFUND = "PREPAID_REFUND", "Prepaid Balance Refunded"
    SETTLEMENT = "SETTLEMENT", "Credit Due Settle"


class CustomerCreditLog(BaseModel):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="credit_logs",
    )
    log_type = models.CharField(
        max_length=20,
        choices=CreditLogType.choices,
        db_index=True,
    )
    old_amount = money_field(default=0, help_text="Balance or limit before this change")
    new_amount = money_field(default=0, help_text="Balance or limit after this change")
    change_amount = money_field(default=0, help_text="Delta amount (+/-)")

    payment_mode = models.CharField(max_length=20, blank=True, help_text="CASH, STAFF_UPI, SHOP_UPI")
    payment_destination = models.CharField(max_length=20, blank=True, help_text="STAFF (staff wallet) or SHOP (shop account)")
    
    notes = models.TextField(blank=True)
    invoice = models.ForeignKey(
        "billing.Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="customer_credit_logs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recorded_customer_credit_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Customer Credit Log"
        verbose_name_plural = "Customer Credit Logs"
        indexes = [
            models.Index(fields=["customer", "log_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.customer.full_name} - {self.get_log_type_display()} ({self.change_amount})"
