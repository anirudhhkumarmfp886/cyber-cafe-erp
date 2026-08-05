"""Tests for the cash book service layer (business rules)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import CashBookEntry
from apps.finance.models.enums import (
    CashEntryCategory,
    CashEntryType,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
)
from apps.finance.services.cashbook_service import CashBookService

User = get_user_model()


class CashBookServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cashbook-user")

    def test_record_income(self):
        entry = CashBookService.record_income(
            amount=2000,
            category=CashEntryCategory.SALES,
            payment_mode="UPI",
            party_name="Customer A",
            by=self.user,
        )
        self.assertEqual(entry.entry_type, CashEntryType.INCOME)
        self.assertTrue(entry.reference_number.startswith("CB-"))
        self.assertTrue(entry.is_income)

    def test_record_expense(self):
        entry = CashBookService.record_expense(
            amount=800,
            category=CashEntryCategory.ELECTRICITY,
            by=self.user,
        )
        self.assertEqual(entry.entry_type, CashEntryType.EXPENSE)
        self.assertFalse(entry.is_income)

    def test_balance_is_income_minus_expense(self):
        CashBookService.record_income(amount=5000, by=self.user)
        CashBookService.record_expense(amount=1200, by=self.user)
        self.assertEqual(CashBookService.balance(), 3800)

    def test_category_must_match_entry_type(self):
        with self.assertRaisesMessage(ValueError, "not valid for"):
            CashBookService.record_expense(
                amount=100,
                category=CashEntryCategory.SALES,
                by=self.user,
            )
        with self.assertRaisesMessage(ValueError, "not valid for"):
            CashBookService.record_income(
                amount=100,
                category=CashEntryCategory.RENT,
                by=self.user,
            )

    def test_income_and_expense_category_sets_are_exclusive(self):
        self.assertFalse(INCOME_CATEGORIES & EXPENSE_CATEGORIES)
        self.assertGreater(len(INCOME_CATEGORIES), 0)
        self.assertGreater(len(EXPENSE_CATEGORIES), 0)

    def test_zero_or_negative_amount_rejected(self):
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            CashBookService.record_income(amount=0, by=self.user)
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            CashBookService.record_expense(amount=-50, by=self.user)

    def test_unknown_payment_mode_rejected(self):
        with self.assertRaisesMessage(ValueError, "Unknown payment mode"):
            CashBookService.record_income(amount=100, payment_mode="BITCOIN", by=self.user)

    def test_day_balance_reflects_entries_up_to_that_day(self):
        CashBookService.record_income(amount=1000, entry_date=date(2026, 1, 1), by=self.user)
        CashBookService.record_expense(amount=200, entry_date=date(2026, 1, 3), by=self.user)
        self.assertEqual(CashBookService.day_balance(date(2026, 1, 2)), 1000)
        self.assertEqual(CashBookService.day_balance(date(2026, 1, 4)), 800)

    def test_soft_delete_removes_from_active_queryset(self):
        entry = CashBookService.record_income(amount=500, by=self.user)
        CashBookService.soft_delete_entry(entry, by=self.user)
        self.assertIsNotNone(entry.deleted_at)
        self.assertEqual(CashBookEntry.objects.count(), 0)
        self.assertEqual(CashBookEntry.all_objects.count(), 1)
        self.assertEqual(CashBookService.balance(), 0)
