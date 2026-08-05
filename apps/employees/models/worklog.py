"""
WorkLogEntry — the daily work log for employees.

An entry records hours worked on a day. Only a supervisor (Manager/Owner)
can approve it; approval credits the employee's wallet automatically as
SALARY using the rate snapshot taken when the entry was created.
"""
from django.conf import settings
from django.db import models

from apps.common.models import BaseModel, money_field


class WorkLogStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class WorkLogEntry(BaseModel):
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="work_logs",
    )
    work_date = models.DateField(db_index=True)

    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    #: Hours worked; derived from start/end when both are given.
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2)

    #: Rate snapshot from the employee at creation time (never recomputed).
    rate_applied = money_field(default=0)
    #: hours * rate, fixed at approval time.
    wage_amount = money_field(default=0)

    status = models.CharField(
        max_length=20, choices=WorkLogStatus.choices, default=WorkLogStatus.PENDING, db_index=True
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        verbose_name = "Work Log Entry"
        verbose_name_plural = "Work Log Entries"
        indexes = [
            models.Index(fields=["employee", "work_date"]),
            models.Index(fields=["status", "work_date"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} · {self.work_date} · {self.status}"
