"""Work entry view tests were retired in Sprint 4.5.

The work-entry counter UI (``workentry:list`` / ``workentry:bill``) was
replaced by the billing surface. Saved work entries were migrated to invoices
by ``billing.0006``. These tests now guard the retirement: the routes must not
resolve and the data layer still works.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from apps.employees.models import Role
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import assign_role_group
from apps.services.services.service_service import ServiceService
from apps.workentry.models import WorkEntry

User = get_user_model()


class WorkEntryRetirementTests(TestCase):
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

    def test_list_route_is_retired(self):
        with self.assertRaises(NoReverseMatch):
            reverse("workentry:list")

    def test_bill_route_is_retired(self):
        entry = WorkEntry.objects.create(
            employee=self.staff,
            service=self.service,
            charged_amount=20,
            created_by=self.staff.user,
            updated_by=self.staff.user,
        )
        with self.assertRaises(NoReverseMatch):
            reverse("workentry:bill", kwargs={"pk": entry.pk})
