"""Tests for customer views + permission enforcement."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.customers.models import Customer
from apps.customers.services.customer_service import CustomerService

User = get_user_model()


class CustomerViewTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.client.login(username="boss", password="OwnerPass#123")

    def test_list_page_shows_customers(self):
        CustomerService.create_customer(data={"full_name": "Ravi Kumar"}, by=self.boss)
        response = self.client.get(reverse("customers:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Kumar")

    def test_list_page_creates_customer(self):
        response = self.client.post(
            reverse("customers:list"),
            {"full_name": "Sunil", "phone": "9998887776"},
        )
        self.assertRedirects(
            response,
            reverse("customers:detail", kwargs={"pk": Customer.objects.get().pk}),
        )
        self.assertEqual(Customer.objects.count(), 1)

    def test_detail_page(self):
        customer = CustomerService.create_customer(data={"full_name": "Ravi"}, by=self.boss)
        response = self.client.get(reverse("customers:detail", kwargs={"pk": customer.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi")

    def test_deactivate_is_post_only(self):
        customer = CustomerService.create_customer(data={"full_name": "Ravi"}, by=self.boss)
        self.client.post(reverse("customers:deactivate", kwargs={"pk": customer.pk}))
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())


class CustomerPermissionTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.staff = User.objects.create_user(username="counter", password="StrongPass#123")
        from apps.employees.models import Role
        from apps.employees.services.role_service import assign_role_group

        assign_role_group(self.staff, Role.STAFF)
        self.client.login(username="counter", password="StrongPass#123")

    def test_staff_can_view_customers_but_not_add(self):
        response = self.client.get(reverse("customers:list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add Customer")

    def test_staff_cannot_create_customer(self):
        response = self.client.post(reverse("customers:list"), {"full_name": "Hacker"})
        self.assertEqual(response.status_code, 403)
