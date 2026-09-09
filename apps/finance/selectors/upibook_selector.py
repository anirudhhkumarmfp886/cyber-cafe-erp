"""UPIBookSelector — read-only access to Shop UPI Book operational ledger data."""
from datetime import date

from django.db.models import Case, F, Q, Sum, When

from apps.finance.models.enums import CashEntryType
from apps.finance.models.upibook import UPIBookEntry


class UPIBookSelector:
    @staticmethod
    def list_entries(filters: dict | None = None):
        filters = filters or {}
        queryset = UPIBookEntry.objects.select_related("bank_account", "staff", "created_by").order_by(
            "-entry_date", "-created_at"
        )

        if filters.get("bank_account"):
            queryset = queryset.filter(bank_account=filters["bank_account"])
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
            q = filters["q"]
            queryset = queryset.filter(
                Q(reference_number__icontains=q)
                | Q(party_name__icontains=q)
                | Q(description__icontains=q)
                | Q(bank_account__account_name__icontains=q)
                | Q(staff__full_name__icontains=q)
            )
        return queryset

    @staticmethod
    def balance(staff=None, bank_account=None) -> float:
        qs = UPIBookEntry.objects.all()
        if staff is not None:
            qs = qs.filter(staff=staff)
        if bank_account is not None:
            qs = qs.filter(bank_account=bank_account)
        total = qs.aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def balance_on(day: date, staff=None, bank_account=None) -> float:
        qs = UPIBookEntry.objects.filter(entry_date__lte=day)
        if staff is not None:
            qs = qs.filter(staff=staff)
        if bank_account is not None:
            qs = qs.filter(bank_account=bank_account)
        total = qs.aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def today_inflow(day=None, staff=None, bank_account=None) -> float:
        day = day or date.today()
        qs = UPIBookEntry.objects.filter(entry_date=day, entry_type=CashEntryType.INCOME)
        if staff is not None:
            qs = qs.filter(staff=staff)
        if bank_account is not None:
            qs = qs.filter(bank_account=bank_account)
        return qs.aggregate(total=Sum("amount"))["total"] or 0

    @staticmethod
    def today_outflow(day=None, staff=None, bank_account=None) -> float:
        day = day or date.today()
        qs = UPIBookEntry.objects.filter(entry_date=day, entry_type=CashEntryType.EXPENSE)
        if staff is not None:
            qs = qs.filter(staff=staff)
        if bank_account is not None:
            qs = qs.filter(bank_account=bank_account)
        return qs.aggregate(total=Sum("amount"))["total"] or 0

    @staticmethod
    def total_balance(account=None) -> float:
        return UPIBookSelector.balance(bank_account=account)
