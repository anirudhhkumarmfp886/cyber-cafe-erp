"""
CashBookService — the only place cash book entries are created or removed.

Validates that the category belongs to the entry type (income categories
only for INCOME entries, expense categories only for EXPENSE entries),
mints a reference number and stamps the responsible employee.
"""
from datetime import date

from django.db import transaction
from django.db.models import Case, F, Sum, When

from apps.common.services.reference_service import ReferenceService
from apps.finance.models import CashBookEntry
from apps.finance.models.enums import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    CashEntryCategory,
    CashEntryType,
)


class CashBookService:
    @staticmethod
    def record_income(
        *,
        amount,
        category: str = CashEntryCategory.SALES,
        payment_mode: str = "CASH",
        party_name: str = "",
        description: str = "",
        entry_date=None,
        by=None,
    ) -> CashBookEntry:
        return CashBookService._record(
            entry_type=CashEntryType.INCOME,
            amount=amount,
            category=category,
            payment_mode=payment_mode,
            party_name=party_name,
            description=description,
            entry_date=entry_date,
            by=by,
        )

    @staticmethod
    def record_expense(
        *,
        amount,
        category: str = CashEntryCategory.MISC,
        payment_mode: str = "CASH",
        party_name: str = "",
        description: str = "",
        entry_date=None,
        by=None,
    ) -> CashBookEntry:
        return CashBookService._record(
            entry_type=CashEntryType.EXPENSE,
            amount=amount,
            category=category,
            payment_mode=payment_mode,
            party_name=party_name,
            description=description,
            entry_date=entry_date,
            by=by,
        )

    @staticmethod
    def _record(
        *,
        entry_type: str,
        amount,
        category: str,
        payment_mode: str,
        party_name: str,
        description: str,
        entry_date,
        by,
    ) -> CashBookEntry:
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        valid_categories = INCOME_CATEGORIES if entry_type == CashEntryType.INCOME else EXPENSE_CATEGORIES
        if category not in valid_categories:
            raise ValueError(f"Category '{category}' is not valid for {entry_type} entries.")
        if payment_mode not in dict(CashBookEntry._meta.get_field("payment_mode").choices):
            raise ValueError(f"Unknown payment mode: {payment_mode}")

        with transaction.atomic():
            return CashBookEntry.objects.create(
                entry_date=entry_date or date.today(),
                entry_type=entry_type,
                category=category,
                payment_mode=payment_mode,
                amount=amount,
                reference_number=ReferenceService.next(ReferenceService.CASH_BOOK),
                party_name=party_name,
                description=description,
                created_by=by,
                updated_by=by,
            )

    @staticmethod
    def balance() -> float:
        """Current cash book balance = total income - total expense."""
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
    def day_balance(day) -> float:
        """Cash balance at the end of a given day."""
        entries = CashBookEntry.objects.filter(entry_date__lte=day)
        total = entries.aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def soft_delete_entry(entry: CashBookEntry, *, by=None) -> CashBookEntry:
        return entry.soft_delete(by=by)
