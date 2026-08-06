"""Tests for service catalog views + permission enforcement."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.services.models import Service
from apps.services.services.service_service import ServiceService

User = get_user_model()


class ServiceViewTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.client.login(username="boss", password="OwnerPass#123")

    def test_list_page_creates_service(self):
        response = self.client.post(
            reverse("services:list"),
            {"name": "Gaming 1hr", "new_category": "Games", "price": "40"},
        )
        self.assertRedirects(
            response,
            reverse("services:detail", kwargs={"pk": Service.objects.get().pk}),
        )
        service = Service.objects.get()
        self.assertEqual(service.price_history.count(), 1)
        self.assertEqual(service.category_name, "Games")

    def test_detail_page_shows_price_history(self):
        service = ServiceService.create_service(data={"name": "Printing", "price": 5}, by=self.boss)
        ServiceService.update_service(service, data={"price": 6}, by=self.boss)
        response = self.client.get(reverse("services:detail", kwargs={"pk": service.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Price History")
        self.assertContains(response, "6.00")

    def test_list_page_filters_by_category(self):
        from apps.services.models import Category

        ServiceService.create_service(
            data={"name": "Gaming 1hr", "new_category": "Games", "price": 40}, by=self.boss
        )
        ServiceService.create_service(
            data={"name": "Printing", "new_category": "Printing", "price": 5}, by=self.boss
        )
        games = Category.objects.get(name="Games")
        response = self.client.get(reverse("services:list"), {"category": str(games.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gaming 1hr")
        self.assertNotContains(response, "\u20b95.00")

    def test_detail_page_updates_price(self):
        service = ServiceService.create_service(data={"name": "Printing", "price": 5}, by=self.boss)
        response = self.client.post(
            reverse("services:detail", kwargs={"pk": service.pk}),
            {"name": "Printing", "new_category": "Printing", "price": "8"},
        )
        self.assertRedirects(response, reverse("services:detail", kwargs={"pk": service.pk}))
        service.refresh_from_db()
        self.assertEqual(service.price, 8)
        self.assertEqual(service.category_name, "Printing")
        self.assertEqual(service.price_history.count(), 2)


class ServicePermissionTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.staff = User.objects.create_user(username="counter", password="StrongPass#123")
        from apps.employees.models import Role
        from apps.employees.services.role_service import assign_role_group

        assign_role_group(self.staff, Role.STAFF)
        self.client.login(username="counter", password="StrongPass#123")

    def test_staff_cannot_create_service(self):
        response = self.client.post(reverse("services:list"), {"name": "X", "price": "1"})
        self.assertEqual(response.status_code, 403)
