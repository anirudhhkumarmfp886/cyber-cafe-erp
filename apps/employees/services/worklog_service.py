"""
WorkLogService — business rules for the daily work log.

Rules enforced here (and nowhere else in the web layer):

  * an entry needs a valid work date and positive hours
  * when both start and end times are given, hours are derived from them
  * the employee's hourly rate is snapshotted at creation time
  * only a PENDING entry can be approved/rejected
  * approval auto-credits the employee wallet as SALARY and stamps the
    approver + timestamp onto the entry (atomic, one ledger row)
"""
from datetime import date, datetime, time
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.employees.models import Employee, WorkLogEntry, WorkLogStatus
from apps.employees.models.wallet import WalletTransactionCategory
from apps.employees.services.wallet_service import WalletService


class WorkLogService:
    @staticmethod
    def _derive_hours(start_time, end_time, hours_worked):
        if start_time and end_time:
            if end_time <= start_time:
                raise ValueError("End time must be after start time.")
            delta = datetime.combine(date.today(), end_time) - datetime.combine(date.today(), start_time)
            derived = round(delta.total_seconds() / 3600, 2)
            if hours_worked is not None and abs(derived - float(hours_worked)) > 0.01:
                raise ValueError("Hours worked do not match the start/end times.")
            return derived
        if hours_worked is None:
            raise ValueError("Enter hours worked or provide both start and end times.")
        return float(hours_worked)

    @staticmethod
    def create_entry(
        *,
        employee: Employee,
        work_date=None,
        hours_worked=None,
        start_time: time = None,
        end_time: time = None,
        notes: str = "",
        by=None,
    ) -> WorkLogEntry:
        if work_date is None:
            raise ValueError("Work date is required.")
        if not employee.is_active:
            raise ValueError("Cannot log work for an inactive employee.")

        hours = WorkLogService._derive_hours(start_time, end_time, hours_worked)
        if hours <= 0:
            raise ValueError("Hours worked must be greater than zero.")

        return WorkLogEntry.objects.create(
            employee=employee,
            work_date=work_date,
            start_time=start_time,
            end_time=end_time,
            hours_worked=hours,
            rate_applied=employee.hourly_rate or 0,
            notes=notes,
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    @transaction.atomic
    def approve_entry(entry: WorkLogEntry, *, by=None) -> WorkLogEntry:
        if entry.status != WorkLogStatus.PENDING:
            raise ValueError("Only pending entries can be approved.")
        if by is None:
            raise ValueError("An approver is required.")

        wage = round(Decimal(entry.hours_worked) * Decimal(entry.rate_applied), 2)
        wallet = WalletService.get_or_create_wallet(entry.employee)
        WalletService.credit(
            wallet=wallet,
            amount=wage,
            category=WalletTransactionCategory.SALARY,
            description=(
                f"Daily work log {entry.work_date} "
                f"({entry.hours_worked}h @ {entry.rate_applied})"
            ),
            source="Daily Work Log",
            destination=entry.employee.full_name,
            by=by,
            entry_date=entry.work_date,
        )

        entry.status = WorkLogStatus.APPROVED
        entry.approved_by = by
        entry.approved_at = timezone.now()
        entry.wage_amount = wage
        entry.updated_by = by
        entry.save(update_fields=["status", "approved_by", "approved_at", "wage_amount", "updated_by", "updated_at"])
        return entry

    @staticmethod
    def reject_entry(entry: WorkLogEntry, *, by=None) -> WorkLogEntry:
        if entry.status != WorkLogStatus.PENDING:
            raise ValueError("Only pending entries can be rejected.")
        entry.status = WorkLogStatus.REJECTED
        entry.approved_by = by
        entry.approved_at = timezone.now()
        entry.updated_by = by
        entry.save(update_fields=["status", "approved_by", "approved_at", "updated_by", "updated_at"])
        return entry
