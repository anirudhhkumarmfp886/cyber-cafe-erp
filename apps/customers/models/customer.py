"""Customer profiles for the ERP (profiles only in Sprint 3 — no wallets)."""
from apps.common.models import BaseModel, money_field
from django.db import models


class Gender(models.TextChoices):
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"
    OTHER = "OTHER", "Other"


class Customer(BaseModel):
    full_name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=15, unique=True, blank=True, db_index=True)
    email = models.EmailField(blank=True)

    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)

    #: Accounting-only control: how much the cafe is willing to extend on credit.
    credit_limit = money_field(default=0, blank=True)
    #: Pre-paid balance the customer has deposited with the shop. Work entries
    #: paid via CUSTOMER_CREDIT settle against this balance first.
    credit_balance = money_field(default=0, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        indexes = [
            models.Index(fields=["full_name", "phone"]),
        ]

    def __str__(self):
        return self.full_name
