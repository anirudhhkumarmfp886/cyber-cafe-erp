"""CashBookSelector — read-only access to cash book data."""
from datetime import date

from django.db.models import Case, F, Q, Sum, When

from apps.finance.models import CashBookEntry
from apps.finance.models.enums import CashEntryType


class CashBookSelector:
    @staticmethod
    def list_entries(filters: dict | None = None):
        queryset = CashBookEntry.objects.order_by("-entry_date", "-created_at")
        filters = filters or {}
        if filters.get("entry_type"):
            queryset = queryset.filter(entry_type=filters["entry_type"])
        if filters.get("category"):
            queryset = queryset.filter(category=filters["category"])
        if filters.get("from_date"):
            queryset = queryset.filter(entry_date__gte=filters["from_date"])
        if filters.get("to_date"):
            queryset = queryset.filter(entry_date__lte=filters["to_date"])
        if filters.get("q"):
            queryset = queryset.filter(
                Q(reference_number__icontains=filters["q"])
                | Q(party_name__icontains=filters["q"])
                | Q(description__icontains=filters["q"])
            )
        return queryset

    @staticmethod
    def get_by_id(entry_id):
        return CashBookEntry.objects.filter(id=entry_id).first()

    @staticmethod
    def balance() -> float:
        total = CashBookEntry.objects.aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def balance_on(day) -> float:
        total = CashBookEntry.objects.filter(entry_date__lte=day).aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def income_total(from_date=None, to_date=None) -> float:
        queryset = CashBookEntry.objects.filter(entry_type=CashEntryType.INCOME)
        if from_date:
            queryset = queryset.filter(entry_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(entry_date__lte=to_date)
        return queryset.aggregate(total=Sum("amount"))["total"] or 0

    @staticmethod
    def expense_total(from_date=None, to_date=None) -> float:
        queryset = CashBookEntry.objects.filter(entry_type=CashEntryType.EXPENSE)
        if from_date:
            queryset = queryset.filter(entry_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(entry_date__lte=to_date)
        return queryset.aggregate(total=Sum("amount"))["total"] or 0
