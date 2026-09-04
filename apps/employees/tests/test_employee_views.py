"""Tests for employee views, permissions and template rendering."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Employee, EmploymentStatus, Role
from apps.employees.services.employee_service import EmployeeService

User = get_user_model()


def _grant(user, *permission_codenames):
    perms = Permission.objects.filter(codename__in=permission_codenames)
    user.user_permissions.add(*perms)


class EmployeeViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-views", password="Password#123")
        _grant(self.owner, "view_employee", "add_employee", "change_employee", "delete_employee")
        self.employee = EmployeeService.create_employee(
            data={
                "username": "view-staff",
                "password": "Password#123",
                "full_name": "View Staff",
                "role": Role.STAFF,
            },
            by=self.owner,
        )

    def test_list_requires_login(self):
        response = self.client.get(reverse("employees:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_list_requires_permission(self):
        User.objects.create_user(username="no-perms", password="Password#123")
        self.client.login(username="no-perms", password="Password#123")
        response = self.client.get(reverse("employees:list"))
        self.assertEqual(response.status_code, 403)

    def test_list_renders_employees(self):
        self.client.login(username="owner-views", password="Password#123")
        response = self.client.get(reverse("employees:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Staff")

    def test_create_employee_via_web(self):
        self.client.login(username="owner-views", password="Password#123")
        response = self.client.post(
            reverse("employees:create"),
            {
                "username": "new-web-staff",
                "password": "WebPass#123",
                "confirm_password": "WebPass#123",
                "full_name": "Web Staff",
                "role": Role.STAFF,
                "status": EmploymentStatus.ACTIVE,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Employee.objects.filter(user__username="new-web-staff").exists())

    def test_password_mismatch_rejected(self):
        self.client.login(username="owner-views", password="Password#123")
        response = self.client.post(
            reverse("employees:create"),
            {
                "username": "mismatch-staff",
                "password": "WebPass#123",
                "confirm_password": "Different#456",
                "full_name": "Mismatch Staff",
                "role": Role.STAFF,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match")
        self.assertFalse(Employee.objects.filter(user__username="mismatch-staff").exists())

    def test_detail_page_renders(self):
        self.client.login(username="owner-views", password="Password#123")
        response = self.client.get(reverse("employees:detail", kwargs={"pk": self.employee.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Staff")

    def test_deactivate_requires_post_and_soft_deletes(self):
        self.client.login(username="owner-views", password="Password#123")
        target = EmployeeService.create_employee(
            data={
                "username": "to-deactivate",
                "password": "Password#123",
                "full_name": "Going Away",
                "role": Role.STAFF,
            },
            by=self.owner,
        )
        response = self.client.post(reverse("employees:deactivate", kwargs={"pk": target.pk}))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertIsNotNone(target.deleted_at)
        self.assertFalse(target.is_active)

    def test_toggle_billing_view_grants_and_revokes(self):
        self.client.login(username="owner-views", password="Password#123")
        target = EmployeeService.create_employee(
            data={
                "username": "toggle-target",
                "password": "Password#123",
                "full_name": "Toggle Staff",
                "role": Role.STAFF,
                "can_create_bills": False,
            },
            by=self.owner,
        )
        self.assertFalse(target.user.has_perm("billing.add_invoice"))

        # First post grants access
        response = self.client.post(reverse("employees:toggle_billing", kwargs={"pk": target.pk}))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertTrue(target.can_create_bills)
        self.assertTrue(target.user.has_perm("billing.add_invoice"))

        # Second post revokes access
        response = self.client.post(reverse("employees:toggle_billing", kwargs={"pk": target.pk}))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.can_create_bills)
        self.assertFalse(target.user.has_perm("billing.add_invoice"))

    def test_toggle_topup_view_grants_and_revokes(self):
        self.client.login(username="owner-views", password="Password#123")
        target = EmployeeService.create_employee(
            data={
                "username": "toggle-topup-target",
                "password": "Password#123",
                "full_name": "Topup Staff",
                "role": Role.STAFF,
                "can_manage_topup": False,
            },
            by=self.owner,
        )
        self.assertFalse(target.user.has_perm("finance.withdraw_shop_cash"))

        # First post grants access
        response = self.client.post(reverse("employees:toggle_topup", kwargs={"pk": target.pk}))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertTrue(target.can_manage_topup)
        self.assertTrue(target.user.has_perm("finance.withdraw_shop_cash"))

        # Second post revokes access
        response = self.client.post(reverse("employees:toggle_topup", kwargs={"pk": target.pk}))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.can_manage_topup)
        self.assertFalse(target.user.has_perm("finance.withdraw_shop_cash"))




class SeedRolesCommandTests(TestCase):
    def test_seed_roles_creates_groups(self):
        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("seed_roles")
        group_names = set(Group.objects.values_list("name", flat=True))
        self.assertIn("Owner", group_names)
        self.assertIn("Manager", group_names)
        self.assertIn("Staff", group_names)

        # Owner/Manager get full permissions, Staff read-only.
        owner_perms = Group.objects.get(name="Owner").permissions.filter(codename__icontains="employee")
        staff_perms = Group.objects.get(name="Staff").permissions.filter(codename__icontains="employee")
        self.assertGreater(owner_perms.count(), staff_perms.count())
        self.assertEqual(set(staff_perms.values_list("codename", flat=True)), {"view_employee"})

    def test_seed_roles_is_idempotent(self):
        from django.core.management import call_command

        call_command("seed_roles")
        call_command("seed_roles")
        from django.contrib.auth.models import Group

        self.assertEqual(Group.objects.filter(name__in=["Owner", "Staff"]).count(), 2)
