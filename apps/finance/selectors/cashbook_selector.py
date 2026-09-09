"""CashBookSelector — read-only access to cash book data."""
from django.db.models import Case, F, Q, Sum, When

from apps.finance.models import CashBookEntry
from apps.finance.models.enums import CashEntryCategory, CashEntryType


class CashBookSelector:
    @staticmethod
    def list_entries(filters: dict | None = None):
        queryset = CashBookEntry.objects.filter(payment_mode="CASH").order_by("-entry_date", "-created_at")
        filters = filters or {}
        if filters.get("staff"):
            queryset = queryset.filter(staff=filters["staff"])
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
    def _base_for_staff(staff=None):
        queryset = CashBookEntry.objects.filter(payment_mode="CASH")
        if staff:
            queryset = queryset.filter(staff=staff)
        return queryset

    @staticmethod
    def balance(staff=None) -> float:
        total = CashBookSelector._base_for_staff(staff).aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def balance_on(day, staff=None) -> float:
        total = CashBookSelector._base_for_staff(staff).filter(entry_date__lte=day).aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def drawer_balance_on(day) -> float:
        """Physical cash balance in the central shop drawer (excluding sales cash held in staff counter floats)."""
        as_on_balance = CashBookSelector.balance_on(day)
        staff_sales_total = (
            CashBookEntry.objects.filter(
                payment_mode="CASH",
                entry_date__lte=day,
                entry_type=CashEntryType.INCOME,
                category=CashEntryCategory.SALES,
                staff__isnull=False,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        return as_on_balance - staff_sales_total

    @staticmethod
    def drawer_balance() -> float:
        """Current physical cash balance in the central shop drawer."""
        total_balance = CashBookSelector.balance()
        staff_sales_total = (
            CashBookEntry.objects.filter(
                payment_mode="CASH",
                entry_type=CashEntryType.INCOME,
                category=CashEntryCategory.SALES,
                staff__isnull=False,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        return total_balance - staff_sales_total

    @staticmethod
    def income_total(from_date=None, to_date=None, staff=None) -> float:
        queryset = CashBookSelector._base_for_staff(staff).filter(entry_type=CashEntryType.INCOME)
        if from_date:
            queryset = queryset.filter(entry_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(entry_date__lte=to_date)
        return queryset.aggregate(total=Sum("amount"))["total"] or 0

    @staticmethod
    def expense_total(from_date=None, to_date=None, staff=None) -> float:
        queryset = CashBookSelector._base_for_staff(staff).filter(entry_type=CashEntryType.EXPENSE)
        if from_date:
            queryset = queryset.filter(entry_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(entry_date__lte=to_date)
        return queryset.aggregate(total=Sum("amount"))["total"] or 0
