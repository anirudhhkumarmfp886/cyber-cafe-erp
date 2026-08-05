"""Tests for the customer service layer (business rules)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Customer
from apps.customers.services.customer_service import CustomerService

User = get_user_model()


class CustomerServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")

    def test_create_customer_minimal(self):
        customer = CustomerService.create_customer(data={"full_name": "Ravi Kumar"}, by=self.user)
        self.assertEqual(customer.full_name, "Ravi Kumar")
        self.assertEqual(customer.credit_limit, 0)
        self.assertTrue(customer.is_active)

    def test_create_requires_name(self):
        with self.assertRaisesMessage(ValueError, "name is required"):
            CustomerService.create_customer(data={"full_name": "  "}, by=self.user)

    def test_create_rejects_duplicate_phone(self):
        CustomerService.create_customer(data={"full_name": "Ravi", "phone": "9876543210"}, by=self.user)
        with self.assertRaisesMessage(ValueError, "phone number already exists"):
            CustomerService.create_customer(data={"full_name": "Sunil", "phone": "9876543210"}, by=self.user)

    def test_create_rejects_negative_credit_limit(self):
        with self.assertRaisesMessage(ValueError, "Credit limit cannot be negative"):
            CustomerService.create_customer(
                data={"full_name": "Ravi", "credit_limit": -5}, by=self.user
            )

    def test_update_customer_changes_fields(self):
        customer = CustomerService.create_customer(data={"full_name": "Ravi"}, by=self.user)
        updated = CustomerService.update_customer(
            customer, data={"full_name": "Ravi Sharma", "city": "Patna"}, by=self.user
        )
        updated.refresh_from_db()
        self.assertEqual(updated.full_name, "Ravi Sharma")
        self.assertEqual(updated.city, "Patna")

    def test_update_rejects_duplicate_phone_on_other(self):
        customer = CustomerService.create_customer(
            data={"full_name": "Ravi", "phone": "111"}, by=self.user
        )
        CustomerService.create_customer(data={"full_name": "Sunil", "phone": "222"}, by=self.user)
        with self.assertRaisesMessage(ValueError, "phone number already exists"):
            CustomerService.update_customer(customer, data={"full_name": "Ravi", "phone": "222"}, by=self.user)

    def test_deactivate_and_restore(self):
        customer = CustomerService.create_customer(data={"full_name": "Ravi"}, by=self.user)
        CustomerService.deactivate_customer(customer, by=self.user)
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())
        self.assertTrue(Customer.all_objects.filter(pk=customer.pk).exists())
        CustomerService.restore_customer(customer, by=self.user)
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
