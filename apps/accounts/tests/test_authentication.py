"""Tests for login flow and brute-force lockout."""
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.services import authentication_service


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = self._make_user("staff1", "Password#123")

    @staticmethod
    def _make_user(username, password):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(username=username, password=password)

    def test_login_page_loads(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username")

    def test_successful_login_redirects(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "staff1", "password": "Password#123"},
        )
        self.assertRedirects(response, reverse("pages:dashboard"))

    def test_failed_login_redirects_back_to_login(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "staff1", "password": "wrong-pass"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password")

    def test_logout_requires_post_and_logs_out(self):
        self.client.login(username="staff1", password="Password#123")
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.client.login(username="staff1", password="Password#123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)


class LockoutTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(username="locked-user", password="Password#123")
        # The locmem cache is process-wide and persists between tests, so the
        # failure counter must be reset per test.
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_lockout_after_threshold_failures(self):
        for _ in range(settings.LOGIN_ATTEMPT_THRESHOLD):
            self.client.post(
                reverse("accounts:login"),
                {"username": "locked-user", "password": "bad"},
            )

        self.assertTrue(authentication_service.is_locked_out("locked-user"))

        # Correct password still rejected because the account is locked.
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "locked-user", "password": "Password#123"},
        )
        self.assertContains(response, "Too many failed login attempts")

    def test_successful_login_clears_attempts(self):
        for _ in range(settings.LOGIN_ATTEMPT_THRESHOLD - 1):
            self.client.post(
                reverse("accounts:login"),
                {"username": "locked-user", "password": "bad"},
            )
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "locked-user", "password": "Password#123"},
        )
        self.assertRedirects(response, reverse("pages:dashboard"))
        self.assertFalse(authentication_service.is_locked_out("locked-user"))
