"""Tests for work log views + approval permission enforcement."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.services.owner_bootstrap_service import OwnerBootstrapService
from apps.employees.models import Role, WorkLogEntry, WorkLogStatus
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService
from apps.employees.services.worklog_service import WorkLogService

User = get_user_model()


class WorkLogViewTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        self.manager = EmployeeService.create_employee(
            data={
                "username": "manager",
                "password": "StrongPass#123",
                "full_name": "The Manager",
                "role": Role.MANAGER,
                "hourly_rate": 100,
            },
            by=self.boss,
        )
        self.staff = EmployeeService.create_employee(
            data={
                "username": "staff",
                "password": "StrongPass#123",
                "full_name": "A Staffer",
                "role": Role.STAFF,
                "hourly_rate": 50,
            },
            by=self.boss,
        )
        self.client.login(username="manager", password="StrongPass#123")

    def test_list_page_shows_entries(self):
        WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        response = self.client.get(reverse("employees:worklog_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A Staffer")

    def test_list_page_creates_entry(self):
        response = self.client.post(
            reverse("employees:worklog_list"),
            {"employee": str(self.staff.pk), "work_date": "2026-08-05", "hours_worked": "8"},
        )
        self.assertRedirects(response, reverse("employees:worklog_list"))
        self.assertEqual(WorkLogEntry.objects.count(), 1)

    def test_approve_action_credits_wallet(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        response = self.client.post(
            reverse("employees:worklog_action", kwargs={"pk": entry.pk, "action": "approve"})
        )
        self.assertRedirects(response, reverse("employees:worklog_list"))
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkLogStatus.APPROVED)
        self.assertEqual(WalletService.balance_of_employee(self.staff), 400)

    def test_reject_action(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        response = self.client.post(
            reverse("employees:worklog_action", kwargs={"pk": entry.pk, "action": "reject"})
        )
        self.assertRedirects(response, reverse("employees:worklog_list"))
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkLogStatus.REJECTED)

    def test_unknown_action_is_ignored(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        self.client.post(reverse("employees:worklog_action", kwargs={"pk": entry.pk, "action": "delete"}))
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkLogStatus.PENDING)


class WorkLogPermissionTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        self.staff = EmployeeService.create_employee(
            data={
                "username": "staff",
                "password": "StrongPass#123",
                "full_name": "A Staffer",
                "role": Role.STAFF,
                "hourly_rate": 50,
            },
            by=self.boss,
        )
        self.client.login(username="staff", password="StrongPass#123")

    def test_staff_cannot_approve(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.staff.user
        )
        response = self.client.post(
            reverse("employees:worklog_action", kwargs={"pk": entry.pk, "action": "approve"})
        )
        self.assertEqual(response.status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkLogStatus.PENDING)
