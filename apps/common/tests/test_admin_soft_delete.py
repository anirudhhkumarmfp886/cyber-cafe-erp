"""
Tests for the BaseAdmin "Show deleted" toggle and the hard-delete / restore
actions in the Django admin.

The toggle flips the changelist between the active-only default manager and
the soft-delete trash. ``hard_delete`` permanently removes rows that are
already soft-deleted, and (because the standard admin delete button is
disabled) falls back to soft-deleting active rows. ``restore_deleted``
brings soft-deleted rows back.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Employee
from apps.employees.services.employee_service import EmployeeService


class AdminSoftDeleteTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            username="super-admin", password="StrongPass#123", email="admin@example.com"
        )
        self.client.force_login(self.owner)
        self.employee = EmployeeService.create_employee(
            data={
                "username": "staff-admin",
                "password": "StrongPass#123",
                "full_name": "Admin Toggle Staff",
                "role": "STAFF",
            },
            by=self.owner,
        )
        self.changelist_url = reverse("admin:employees_employee_changelist")

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------
    def test_toggle_links_rendered(self):
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Show deleted")

        response = self.client.get(self.changelist_url, {"deleted": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hide deleted")

    def test_deleted_rows_hidden_by_default(self):
        self.employee.soft_delete(by=self.owner)

        response = self.client.get(self.changelist_url)
        self.assertNotContains(response, self.employee.full_name)

    def test_deleted_rows_shown_when_toggled(self):
        self.employee.soft_delete(by=self.owner)

        response = self.client.get(self.changelist_url, {"deleted": "1"})
        self.assertContains(response, self.employee.full_name)

    def test_toggle_keeps_existing_filters(self):
        # Active view with a filter -> "Show deleted" keeps role and adds deleted.
        response = self.client.get(self.changelist_url, {"role": "STAFF"})
        self.assertContains(response, "Show deleted")
        self.assertContains(response, "deleted=1")
        self.assertContains(response, "role=STAFF")

        # Deleted view with the same filter -> "Hide deleted" keeps role, drops deleted.
        response = self.client.get(self.changelist_url, {"deleted": "1", "role": "STAFF"})
        self.assertContains(response, "Hide deleted")
        self.assertNotContains(response, "deleted=1")
        self.assertContains(response, "role=STAFF")

    # ------------------------------------------------------------------
    # hard_delete
    # ------------------------------------------------------------------
    def test_hard_delete_permanently_removes_soft_deleted_row(self):
        self.employee.soft_delete(by=self.owner)

        response = self.client.post(
            self.changelist_url,
            {
                "action": "hard_delete",
                "index": "0",
                "_selected_action": [str(self.employee.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Employee.all_objects.filter(pk=self.employee.pk).exists())

    def test_hard_delete_soft_deletes_active_row_instead(self):
        response = self.client.post(
            self.changelist_url,
            {
                "action": "hard_delete",
                "index": "0",
                "_selected_action": [str(self.employee.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertIsNotNone(self.employee.deleted_at)
        self.assertTrue(Employee.all_objects.filter(pk=self.employee.pk).exists())

    # ------------------------------------------------------------------
    # restore_deleted
    # ------------------------------------------------------------------
    def test_restore_brings_soft_deleted_row_back(self):
        self.employee.soft_delete(by=self.owner)

        response = self.client.post(
            self.changelist_url,
            {
                "action": "restore_deleted",
                "index": "0",
                "_selected_action": [str(self.employee.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.deleted_at)
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())

    def test_restore_skips_active_rows(self):
        response = self.client.post(
            self.changelist_url,
            {
                "action": "restore_deleted",
                "index": "0",
                "_selected_action": [str(self.employee.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.deleted_at)
