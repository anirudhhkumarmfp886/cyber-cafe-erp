"""Read-only queries behind the work entry pages."""
from django.db.models import Q, Sum

from apps.workentry.models import WorkEntry


class WorkEntrySelector:
    @staticmethod
    def list_entries(filters: dict, staff=None, is_manager: bool = False):
        """Work entries with optional staff scoping + date/status/search filters.

        Staff only see their own entries unless ``is_manager`` is True.
        """
        qs = (
            WorkEntry.objects.select_related("customer", "service", "employee")
            .order_by("-entry_date", "-created_at")
        )
        if staff is not None and not is_manager:
            qs = qs.filter(employee=staff)

        if filters.get("status"):
            qs = qs.filter(status=filters["status"])
        if filters.get("staff") and is_manager:
            qs = qs.filter(employee_id=filters["staff"])
        if filters.get("from_date"):
            qs = qs.filter(entry_date__gte=filters["from_date"])
        if filters.get("to_date"):
            qs = qs.filter(entry_date__lte=filters["to_date"])
        q = (filters.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(reference_number__icontains=q)
                | Q(customer_name__icontains=q)
                | Q(customer__full_name__icontains=q)
            )
        return qs

    @staticmethod
    def income_totals(qs):
        """Aggregate income / total across a filtered queryset (for the list)."""
        agg = qs.aggregate(
            income=Sum("income"),
            billed=Sum("total"),
        )
        return {
            "income": agg["income"] or 0,
            "billed": agg["billed"] or 0,
        }