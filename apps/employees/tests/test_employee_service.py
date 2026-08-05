"""Tests for the employee service layer (business rules)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import Employee, Role
from apps.employees.services.employee_service import EmployeeService

User = get_user_model()


class EmployeeServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-service")

    def _payload(self, **overrides):
        data = {
            "username": "staff-service",
            "password": "StrongPass#123",
            "full_name": "Service Staff",
            "role": Role.STAFF,
        }
        data.update(overrides)
        return data

    def test_create_employee_creates_user_and_profile(self):
        employee = EmployeeService.create_employee(data=self._payload(), by=self.owner)

        self.assertTrue(User.objects.filter(username="staff-service").exists())
        self.assertTrue(Employee.objects.filter(pk=employee.pk).exists())
        self.assertEqual(employee.full_name, "Service Staff")
        self.assertEqual(employee.created_by, self.owner)
        self.assertIsNotNone(employee.employee_code)
        self.assertEqual(employee.employee_code, "ANC-0001")

    def test_employee_codes_are_sequential(self):
        EmployeeService.create_employee(data=self._payload(username="one"), by=self.owner)
        EmployeeService.create_employee(data=self._payload(username="two"), by=self.owner)

        codes = list(Employee.objects.order_by("employee_code").values_list("employee_code", flat=True))
        self.assertEqual(codes, ["ANC-0001", "ANC-0002"])

    def test_duplicate_username_rejected(self):
        EmployeeService.create_employee(data=self._payload(), by=self.owner)
        with self.assertRaises(ValueError):
            EmployeeService.create_employee(data=self._payload(username="staff-service"), by=self.owner)

    def test_role_group_is_assigned_and_synced(self):
        employee = EmployeeService.create_employee(data=self._payload(), by=self.owner)
        self.assertTrue(employee.user.groups.filter(name="Staff").exists())

        EmployeeService.update_employee(employee, data={"role": Role.MANAGER}, by=self.owner)
        employee.refresh_from_db()
        self.assertEqual(employee.role, Role.MANAGER)
        self.assertTrue(employee.user.groups.filter(name="Manager").exists())
        self.assertFalse(employee.user.groups.filter(name="Staff").exists())

    def test_deactivate_soft_deletes_and_locks_login(self):
        employee = EmployeeService.create_employee(data=self._payload(), by=self.owner)
        employee = EmployeeService.deactivate_employee(employee, by=self.owner)

        self.assertIsNotNone(employee.deleted_at)
        self.assertFalse(employee.is_active)
        employee.user.refresh_from_db()
        self.assertFalse(employee.user.is_active)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(Employee.all_objects.count(), 1)

    def test_restore_reactivates(self):
        employee = EmployeeService.create_employee(data=self._payload(), by=self.owner)
        employee = EmployeeService.deactivate_employee(employee, by=self.owner)
        employee = EmployeeService.restore_employee(employee, by=self.owner)

        self.assertTrue(employee.is_active)
        self.assertIsNone(employee.deleted_at)
        employee.user.refresh_from_db()
        self.assertTrue(employee.user.is_active)
