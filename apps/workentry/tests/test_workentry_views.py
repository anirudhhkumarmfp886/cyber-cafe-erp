"""Tests for work entry views (counter page + editable bill)."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Role
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import assign_role_group
from apps.finance.models import CashBookEntry
from apps.finance.models.enums import CashEntryCategory
from apps.finance.services.bank_service import BankService
from apps.services.services.service_service import ServiceService
from apps.workentry.models import WorkEntry, WorkEntryStatus

User = get_user_model()


class WorkEntryViewTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = User.objects.create_superuser(username="we-boss", password="OwnerPass#123")
        self.staff = EmployeeService.create_employee(
            data={
                "username": "we-view-staff",
                "password": "StrongPass#123",
                "full_name": "View Staff",
                "role": Role.COUNTER_STAFF,
            },
            by=self.owner,
        )
        assign_role_group(self.staff.user, Role.COUNTER_STAFF)
        self.service = ServiceService.create_service(
            data={"name": "Printing B/W", "price": 20}, by=self.owner
        )
        self.account = BankService.create_account(
            account_name="HDFC Main", bank_name="HDFC", account_number="9002", by=self.owner
        )

    def _login(self, user=None):
        user = user or self.staff.user
        self.client.force_login(user)
        return user

    def test_list_requires_login(self):
        response = self.client.get(reverse("workentry:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_counter_staff_can_open_list(self):
        self._login()
        response = self.client.get(reverse("workentry:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Work Entry")

    def test_create_draft_via_post_redirects_to_bill(self):
        self._login()
        data = {
            "entry_date": "",
            "customer": "",
            "customer_name": "Walk-in",
            "service": str(self.service.pk),
            "page_quantity": "10",
            "charged_amount": "20",
            "payment_mode": "CASH",
            "credit_rest_mode": "",
            "bank_account": "",
            "transfer_to_customer": "0",
            "transfer_on_behalf": "0",
            "cash_withdrawal": "0",
            "notes": "",
        }
        response = self.client.post(reverse("workentry:list"), data)
        self.assertEqual(response.status_code, 302)
        entry = WorkEntry.objects.get()
        self.assertEqual(entry.status, WorkEntryStatus.DRAFT)
        self.assertEqual(entry.employee, self.staff)
        self.assertIn(reverse("workentry:bill", kwargs={"pk": entry.pk}), response.url)

    def test_bill_page_editable_for_draft(self):
        self._login()
        entry = WorkEntry.objects.create(
            employee=self.staff,
            service=self.service,
            charged_amount=20,
            created_by=self.staff.user,
            updated_by=self.staff.user,
        )
        response = self.client.get(reverse("workentry:bill", kwargs={"pk": entry.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save Bill")

    def test_save_bill_books_ledgers(self):
        self._login()
        entry = WorkEntry.objects.create(
            employee=self.staff,
            service=self.service,
            charged_amount=20,
            created_by=self.staff.user,
            updated_by=self.staff.user,
        )
        data = {
            "entry_date": "2026-01-15",
            "customer": "",
            "customer_name": "",
            "service": str(self.service.pk),
            "page_quantity": "0",
            "charged_amount": "20",
            "payment_mode": "CASH",
            "credit_rest_mode": "",
            "bank_account": "",
            "transfer_to_customer": "0",
            "transfer_on_behalf": "0",
            "cash_withdrawal": "0",
            "notes": "",
        }
        response = self.client.post(reverse("workentry:bill", kwargs={"pk": entry.pk}), data)
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkEntryStatus.SAVED)
        self.assertEqual(entry.income, 20)
        self.assertEqual(CashBookEntry.objects.get(category=CashEntryCategory.SALES).amount, 20)

    def test_saved_bill_is_read_only(self):
        self._login()
        entry = WorkEntry.objects.create(
            employee=self.staff,
            service=self.service,
            charged_amount=20,
            created_by=self.staff.user,
            updated_by=self.staff.user,
        )
        from apps.workentry.services.workentry_service import WorkEntryService

        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        response = self.client.get(reverse("workentry:bill", kwargs={"pk": entry.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Save Bill")
        self.assertContains(response, "Saved &amp; booked")

    def test_staff_cannot_open_other_staffs_draft(self):
        colleague = EmployeeService.create_employee(
            data={
                "username": "we-other",
                "password": "StrongPass#123",
                "full_name": "Other Staff",
                "role": Role.COUNTER_STAFF,
            },
            by=self.owner,
        )
        entry = WorkEntry.objects.create(
            employee=colleague,
            service=self.service,
            charged_amount=20,
            created_by=colleague.user,
            updated_by=colleague.user,
        )
        self._login(self.staff.user)
        response = self.client.get(reverse("workentry:bill", kwargs={"pk": entry.pk}))
        self.assertEqual(response.status_code, 403)
