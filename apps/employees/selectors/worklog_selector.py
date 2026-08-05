"""
WorkLogSelector — read-only access to work log entries for views/templates.
"""
from django.db.models import F, Q, Sum

from apps.employees.models import WorkLogEntry, WorkLogStatus


class WorkLogSelector:
    @staticmethod
    def list_entries(filters: dict):
        queryset = WorkLogEntry.objects.select_related("employee", "employee__user").order_by(
            "-work_date", "-created_at"
        )
        employee_id = filters.get("employee")
        status = filters.get("status")
        from_date = filters.get("from_date")
        to_date = filters.get("to_date")
        q = filters.get("q", "")

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if status and status in WorkLogStatus.values:
            queryset = queryset.filter(status=status)
        if from_date:
            queryset = queryset.filter(work_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(work_date__lte=to_date)
        if q:
            queryset = queryset.filter(
                Q(employee__full_name__icontains=q) | Q(employee__employee_code__icontains=q)
            )
        return queryset

    @staticmethod
    def get_by_id(entry_id):
        return WorkLogEntry.objects.select_related("employee").filter(id=entry_id).first()

    @staticmethod
    def pending_count() -> int:
        return WorkLogEntry.objects.filter(status=WorkLogStatus.PENDING).count()

    @staticmethod
    def pending_wages() -> float:
        """Sum of wage_amount for pending entries (rate snapshot based)."""
        total = WorkLogEntry.objects.filter(
            status=WorkLogStatus.PENDING
        ).aggregate(total=Sum(F("hours_worked") * F("rate_applied")))["total"]
        return float(total or 0)
