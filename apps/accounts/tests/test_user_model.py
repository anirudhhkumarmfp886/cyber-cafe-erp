"""Tests for the custom User model and manager."""
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user_without_password(self):
        user = User.objects.create_user(username="no-pass")
        self.assertEqual(user.username, "no-pass")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())

    def test_create_superuser(self):
        user = User.objects.create_superuser(username="root", password="RootPass#1")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("RootPass#1"))

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="dup")
        with self.assertRaises(Exception):
            User.objects.create_user(username="dup")

    def test_get_full_name_falls_back_to_username(self):
        user = User.objects.create_user(username="only-user")
        self.assertEqual(user.get_full_name(), "only-user")

    def test_soft_deleted_user_cannot_authenticate(self):
        user = User.objects.create_user(username="gone", password="Password#123")
        self.client.login(username="gone", password="Password#123")
        user.soft_delete()
        self.assertFalse(self.client.login(username="gone", password="Password#123"))

    def test_str_representation(self):
        user = User.objects.create_user(username="shown")
        self.assertEqual(str(user), "shown")
