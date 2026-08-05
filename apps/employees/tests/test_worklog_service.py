"""Tests for the daily work log service (business rules)."""
from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.services.owner_bootstrap_service import OwnerBootstrapService
from apps.employees.models import Role, WorkLogEntry, WorkLogStatus
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService
from apps.employees.services.worklog_service import WorkLogService

User = get_user_model()


class WorkLogServiceTests(TestCase):
    def setUp(self):
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

    def test_create_entry_with_manual_hours(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        self.assertEqual(entry.hours_worked, 8)
        self.assertEqual(entry.rate_applied, 50)
        self.assertEqual(entry.status, WorkLogStatus.PENDING)

    def test_create_entry_derives_hours_from_times(self):
        entry = WorkLogService.create_entry(
            employee=self.staff,
            work_date=date(2026, 8, 5),
            start_time=time(9, 0),
            end_time=time(17, 30),
            by=self.manager.user,
        )
        self.assertEqual(float(entry.hours_worked), 8.5)

    def test_create_entry_rejects_end_before_start(self):
        with self.assertRaisesMessage(ValueError, "End time must be after start time"):
            WorkLogService.create_entry(
                employee=self.staff,
                work_date=date(2026, 8, 5),
                start_time=time(17, 0),
                end_time=time(9, 0),
                by=self.manager.user,
            )

    def test_create_entry_rejects_missing_hours(self):
        with self.assertRaisesMessage(ValueError, "Enter hours worked"):
            WorkLogService.create_entry(employee=self.staff, work_date=date(2026, 8, 5), by=self.manager.user)

    def test_create_entry_rejects_inactive_employee(self):
        EmployeeService.deactivate_employee(self.staff, by=self.manager.user)
        with self.assertRaisesMessage(ValueError, "inactive employee"):
            WorkLogService.create_entry(
                employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
            )

    def test_approve_credits_salary_to_wallet(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        WorkLogService.approve_entry(entry, by=self.manager.user)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkLogStatus.APPROVED)
        self.assertEqual(entry.wage_amount, 400)
        self.assertEqual(WalletService.balance_of_employee(self.staff), 400)

    def test_approve_wage_uses_rate_snapshot(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        EmployeeService.update_employee(self.staff, data={"hourly_rate": 99}, by=self.manager.user)
        WorkLogService.approve_entry(entry, by=self.manager.user)
        entry.refresh_from_db()
        self.assertEqual(entry.wage_amount, 400)

    def test_approve_requires_pending(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        WorkLogService.approve_entry(entry, by=self.manager.user)
        with self.assertRaisesMessage(ValueError, "Only pending entries"):
            WorkLogService.approve_entry(entry, by=self.manager.user)

    def test_reject_no_wallet_credit(self):
        entry = WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        WorkLogService.reject_entry(entry, by=self.manager.user)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkLogStatus.REJECTED)
        self.assertEqual(WalletService.balance_of_employee(self.staff), 0)

    def test_work_log_entries_are_counted(self):
        WorkLogService.create_entry(
            employee=self.staff, work_date=date(2026, 8, 5), hours_worked=8, by=self.manager.user
        )
        self.assertEqual(WorkLogEntry.objects.count(), 1)
