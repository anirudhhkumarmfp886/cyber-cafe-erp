"""Tests for first-run owner bootstrap (signup)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.services.owner_bootstrap_service import OwnerBootstrapService
from apps.employees.models import Employee, Role, WalletType
from apps.employees.services.wallet_service import WalletService

User = get_user_model()


class OwnerBootstrapServiceTests(TestCase):
    def test_bootstrap_required_when_no_superuser(self):
        self.assertTrue(OwnerBootstrapService.is_bootstrap_required())

    def test_create_owner_builds_superuser_employee_and_wallet(self):
        user = OwnerBootstrapService.create_owner(
            username="boss", password="OwnerPass#123", email="boss@example.com"
        )
        user.refresh_from_db()
        self.assertTrue(user.is_superuser)
        employee = Employee.objects.get(user=user)
        self.assertEqual(employee.role, Role.OWNER)
        self.assertEqual(employee.status, "ACTIVE")
        # Wallets are minted lazily per type (CASH + ONLINE) via get_or_create.
        self.assertEqual(
            WalletService.balance_of(WalletService.get_or_create_wallet(employee, WalletType.CASH)),
            0,
        )
        self.assertTrue(OwnerBootstrapService.is_bootstrap_required() is False)

    def test_second_owner_rejected(self):
        OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        with self.assertRaisesMessage(ValueError, "Signup is disabled"):
            OwnerBootstrapService.create_owner(username="boss2", password="OwnerPass#123")


class OwnerSignupViewTests(TestCase):
    def test_signup_page_available_before_owner(self):
        response = self.client.get(reverse("accounts:signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set up AK Nazar Cyber Cafe ERP")

    def test_signup_creates_owner_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {"username": "boss", "password": "OwnerPass#123", "confirm_password": "OwnerPass#123"},
        )
        self.assertRedirects(response, reverse("pages:dashboard"))
        self.assertTrue(User.objects.filter(username="boss", is_superuser=True).exists())
        self.assertEqual(self.client.session["_auth_user_id"], str(User.objects.get(username="boss").pk))

    def test_signup_password_mismatch_rejected(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {"username": "boss", "password": "OwnerPass#123", "confirm_password": "Different#123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match")
        self.assertFalse(User.objects.filter(username="boss").exists())

    def test_signup_disabled_after_owner_exists(self):
        OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        response = self.client.get(reverse("accounts:signup"))
        self.assertRedirects(response, reverse("accounts:login"))

    def test_duplicate_username_rejected(self):
        OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        # Owner exists -> signup page itself is gone, so directly test the form.
        from apps.accounts.forms import OwnerSignupForm

        form = OwnerSignupForm(
            data={"username": "boss", "password": "OwnerPass#123", "confirm_password": "OwnerPass#123"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("already taken", form.errors.get("username", [])[0])

    def test_login_page_shows_signup_link_before_owner(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "Create the owner account")

    def test_login_page_hides_signup_link_after_owner(self):
        OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "Create the owner account")