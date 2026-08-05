"""
Tests for the common BaseModel audit + soft-delete foundation.

BaseModel is abstract, so behaviour is verified through the two concrete
models that inherit it today: accounts.User and employees.Employee.
"""
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.common.middleware import CurrentUserMiddleware, get_current_user
from apps.employees.models import Employee
from apps.employees.services.employee_service import EmployeeService


class SoftDeleteBehaviourTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="owner-audit")
        self.employee = EmployeeService.create_employee(
            data={
                "username": "staff-audit",
                "password": "StrongPass#123",
                "full_name": "Audit Staff",
                "role": "STAFF",
            },
            by=self.owner,
        )

    def test_objects_manager_hides_soft_deleted(self):
        self.assertEqual(Employee.objects.count(), 1)

        self.employee.soft_delete(by=self.owner)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(Employee.all_objects.count(), 1)

    def test_restore_brings_record_back(self):
        self.employee.soft_delete(by=self.owner)
        self.employee.restore(by=self.owner)

        self.assertEqual(Employee.objects.count(), 1)
        self.assertTrue(self.employee.is_active)
        self.assertIsNone(self.employee.deleted_at)

    def test_soft_delete_sets_audit_fields(self):
        self.employee.soft_delete(by=self.owner)
        self.employee.refresh_from_db()

        self.assertFalse(self.employee.is_active)
        self.assertIsNotNone(self.employee.deleted_at)
        self.assertEqual(self.employee.deleted_by, self.owner)

    def test_deleted_at_not_required_by_default(self):
        self.assertIsNone(self.employee.deleted_at)
        self.assertTrue(self.employee.is_active)


class AuditFieldTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="owner-middleware")

    def test_created_by_populated_inside_request(self):
        """CurrentUserMiddleware + BaseModel.save must stamp created_by."""
        request = RequestFactory().get("/")
        request.user = self.owner
        holder = {}

        def get_response(request):
            employee = EmployeeService.create_employee(
                data={
                    "username": "staff-middleware",
                    "password": "StrongPass#123",
                    "full_name": "Middleware Staff",
                    "role": "STAFF",
                },
                by=self.owner,
            )
            holder["employee"] = employee
            return HttpResponse("ok")

        CurrentUserMiddleware(get_response)(request)

        self.assertEqual(holder["employee"].created_by, self.owner)
        self.assertIsNone(get_current_user(), "thread-local user must be cleared after request")
