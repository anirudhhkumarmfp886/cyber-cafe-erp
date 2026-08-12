"""Tests for Phase 1 cash book: per-staff books, custom permissions, owner cash."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Role
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import assign_role_group
from apps.finance.forms.cashbook import CashBookEntryForm
from apps.finance.models import CashBookEntry
from apps.finance.models.enums import (
    CashEntryCategory,
    CashEntryType,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
)
from apps.finance.selectors.cashbook_selector import CashBookSelector
from apps.finance.services.cashbook_service import CashBookService

User = get_user_model()


class CashBookStaffTests(TestCase):
    def setUp(self):
        self.owner = EmployeeService.create_employee(
            data={"username": "cash-owner", "password": "Pass#123", "full_name": "Owner One", "role": Role.OWNER}
        )
        self.staff = EmployeeService.create_employee(
            data={"username": "cash-staff", "password": "Pass#123", "full_name": "Staff Two", "role": Role.STAFF}
        )
        self.other = EmployeeService.create_employee(
            data={"username": "cash-other", "password": "Pass#123", "full_name": "Staff Three", "role": Role.STAFF}
        )
        self.owner_user = self.owner.user
        self.staff_user = self.staff.user
        self.other_user = self.other.user

    def test_staff_auto_attributed_from_user(self):
        entry = CashBookService.record_income(amount=500, by=self.staff_user)
        self.assertEqual(entry.staff, self.staff)

    def test_explicit_staff_override(self):
        entry = CashBookService.record_expense(
            amount=100, by=self.owner_user, staff=self.staff
        )
        self.assertEqual(entry.staff, self.staff)

    def test_entries_without_user_have_no_staff(self):
        entry = CashBookService.record_income(amount=500)
        self.assertIsNone(entry.staff)

    def test_staff_scoped_balance_and_totals(self):
        CashBookService.record_income(amount=1000, by=self.staff_user)
        CashBookService.record_expense(amount=200, by=self.staff_user)
        CashBookService.record_income(amount=7000, by=self.other_user)
        self.assertEqual(CashBookSelector.balance(staff=self.staff), 800)
        self.assertEqual(CashBookSelector.balance(staff=self.other), 7000)
        self.assertEqual(CashBookSelector.balance(), 7800)
        self.assertEqual(
            CashBookSelector.income_total(staff=self.staff), 1000
        )
        self.assertEqual(
            CashBookSelector.expense_total(staff=self.staff), 200
        )

    def test_staff_scoped_balance_on_date(self):
        CashBookService.record_income(
            amount=1000, entry_date=date(2026, 1, 1), by=self.staff_user
        )
        CashBookService.record_income(
            amount=2000, entry_date=date(2026, 1, 5), by=self.staff_user
        )
        self.assertEqual(
            CashBookSelector.balance_on(date(2026, 1, 3), staff=self.staff), 1000
        )

    def test_staff_scoped_list_entries(self):
        CashBookService.record_income(amount=500, by=self.staff_user)
        CashBookService.record_income(amount=900, by=self.other_user)
        rows = CashBookSelector.list_entries({"staff": self.staff})
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().staff, self.staff)

    def test_owner_withdraw_is_expense_entry(self):
        entry = CashBookService.owner_withdraw(amount=3000, by=self.owner_user)
        self.assertEqual(entry.entry_type, CashEntryType.EXPENSE)
        self.assertEqual(entry.category, CashEntryCategory.OWNER_WITHDRAWAL)
        self.assertEqual(entry.party_name, "Owner")
        self.assertIn(CashEntryCategory.OWNER_WITHDRAWAL, EXPENSE_CATEGORIES)

    def test_owner_deposit_is_income_entry(self):
        entry = CashBookService.owner_deposit(amount=5000, by=self.owner_user)
        self.assertEqual(entry.entry_type, CashEntryType.INCOME)
        self.assertEqual(entry.category, CashEntryCategory.OWNER_DEPOSIT)
        self.assertIn(CashEntryCategory.OWNER_DEPOSIT, INCOME_CATEGORIES)

    def test_owner_cash_staff_defaults_to_operator(self):
        entry = CashBookService.owner_withdraw(amount=1000, by=self.owner_user)
        self.assertEqual(entry.staff, self.owner)

    def test_custom_permissions_exist(self):
        content_type = ContentType.objects.get_for_model(CashBookEntry)
        codenames = {
            p.codename
            for p in content_type.permission_set.all()
        }
        self.assertIn("add_cashbookincome", codenames)
        self.assertIn("add_cashbookexpense", codenames)
        self.assertIn("withdraw_shop_cash", codenames)

    def test_seed_roles_grants_cash_permissions(self):
        call_command("seed_roles")
        for user, role in [
            (self.owner_user, Role.OWNER),
            (self.staff_user, Role.STAFF),
        ]:
            assign_role_group(user, role)
        self.assertTrue(self.owner_user.has_perm("finance.add_cashbookincome"))
        self.assertTrue(self.owner_user.has_perm("finance.add_cashbookexpense"))
        self.assertTrue(self.owner_user.has_perm("finance.withdraw_shop_cash"))
        self.assertFalse(self.staff_user.has_perm("finance.add_cashbookincome"))
        self.assertFalse(self.staff_user.has_perm("finance.add_cashbookexpense"))


class CashBookFormPermissionTests(TestCase):
    def test_form_restricts_entry_type_choices(self):
        form = CashBookEntryForm(allowed_entry_types=("INCOME",))
        choices = [value for value, _ in form.fields["entry_type"].choices]
        self.assertEqual(choices, ["INCOME"])

    def test_form_with_no_allowed_types_shows_all(self):
        form = CashBookEntryForm()
        choices = [value for value, _ in form.fields["entry_type"].choices]
        self.assertEqual(set(choices), {CashEntryType.INCOME, CashEntryType.EXPENSE})

    def test_form_rejects_wrong_category_for_type(self):
        form = CashBookEntryForm(
            data={
                "entry_type": "INCOME",
                "category": "RENT",
                "payment_mode": "CASH",
                "amount": "100",
            }
        )
        self.assertFalse(form.is_valid())

    def test_income_only_form_restricts_categories(self):
        form = CashBookEntryForm(allowed_entry_types=("INCOME",))
        categories = {value for value, _ in form.fields["category"].choices}
        self.assertEqual(categories, set(INCOME_CATEGORIES))
        self.assertNotIn(CashEntryCategory.RENT, categories)


class CashBookViewTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = EmployeeService.create_employee(
            data={"username": "view-owner", "password": "Pass#123", "full_name": "View Owner", "role": Role.OWNER}
        )
        self.staff = EmployeeService.create_employee(
            data={"username": "view-staff", "password": "Pass#123", "full_name": "View Staff", "role": Role.STAFF}
        )
        self.staff_user = self.staff.user

    def _url(self):
        return reverse("finance:cashbook_list")

    def test_owner_sees_shop_cash_book_and_owner_cash_card(self):
        CashBookService.record_income(amount=1000, by=self.owner.user)
        self.client.login(username="view-owner", password="Pass#123")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shop Cash Book")
        self.assertContains(response, "Owner Cash")
        self.assertEqual(response.context["staff"], None)
        self.assertEqual(response.context["balance"], 1000)

    def test_staff_sees_only_own_entries(self):
        CashBookService.record_income(amount=1000, by=self.staff_user)
        CashBookService.record_income(amount=5000, by=self.owner.user)
        self.client.login(username="view-staff", password="Pass#123")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["staff"], self.staff)
        self.assertEqual(response.context["staff_label"], "View Staff")
        self.assertEqual(response.context["balance"], 1000)
        self.assertIsNone(response.context["owner_cash_form"])
        self.assertNotIn("Owner Cash", response.content.decode())

    def test_staff_cannot_record_expense(self):
        self.client.login(username="view-staff", password="Pass#123")
        response = self.client.post(
            self._url(),
            {
                "entry_type": "EXPENSE",
                "category": "RENT",
                "payment_mode": "CASH",
                "amount": "100",
                "party_name": "",
                "description": "",
                "entry_date": "",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_records_income_and_expense(self):
        self.client.login(username="view-owner", password="Pass#123")
        response = self.client.post(
            self._url(),
            {
                "entry_type": "INCOME",
                "category": "OTHER_INCOME",
                "payment_mode": "CASH",
                "amount": "250",
                "party_name": "Party X",
                "description": "",
                "entry_date": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CashBookEntry.objects.count(), 1)
        self.assertEqual(CashBookEntry.objects.get().entry_type, CashEntryType.INCOME)

    def test_owner_cash_withdraw_via_web(self):
        self.client.login(username="view-owner", password="Pass#123")
        response = self.client.post(
            reverse("finance:cashbook_owner_cash"),
            {"action": "WITHDRAW", "amount": "2000", "payment_mode": "CASH", "description": "personal"},
        )
        self.assertEqual(response.status_code, 302)
        entry = CashBookEntry.objects.get()
        self.assertEqual(entry.category, CashEntryCategory.OWNER_WITHDRAWAL)
        self.assertEqual(entry.entry_type, CashEntryType.EXPENSE)

    def test_staff_scoped_as_on_balance(self):
        CashBookService.record_income(amount=1000, entry_date=date(2026, 1, 1), by=self.staff_user)
        CashBookService.record_income(amount=500, entry_date=date(2026, 1, 2), by=self.owner.user)
        self.client.login(username="view-staff", password="Pass#123")
        response = self.client.get(self._url(), {"as_on": "2026-01-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["as_on_balance"], 1000)
