"""Tests for Phase 1 quick customer add on the billing screen."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.billing.forms.invoice import InvoiceLineFormSet
from apps.billing.models import Invoice
from apps.customers.models import Customer
from apps.employees.models import Role
from apps.employees.services.role_service import assign_role_group
from apps.services.services.service_service import ServiceService

User = get_user_model()


def _line_data(service_pk, qty):
    formset = InvoiceLineFormSet(instance=Invoice(), prefix="line")
    return {
        f"{formset.prefix}-TOTAL_FORMS": "1",
        f"{formset.prefix}-INITIAL_FORMS": "0",
        f"{formset.prefix}-MIN_NUM_FORMS": "1",
        f"{formset.prefix}-MAX_NUM_FORMS": "1000",
        f"{formset.prefix}-0-service": str(service_pk),
        f"{formset.prefix}-0-qty": str(qty),
        f"{formset.prefix}-0-id": "",
    }


class QuickCustomerTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.client.login(username="boss", password="OwnerPass#123")
        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "category": "GAMES", "price": 40}, by=self.boss
        )

    def _post(self, **overrides):
        data = {
            "customer": "",
            "customer_name": "Ajay New",
            "create_customer": "on",
            "payment_mode": "CASH",
            "discount": "0",
            "notes": "",
        }
        data.update(overrides)
        data.update(_line_data(self.gaming.pk, 1))
        return self.client.post(reverse("billing:list"), data)

    def test_quick_customer_creates_customer_and_links_invoice(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get()
        self.assertEqual(customer.full_name, "Ajay New")
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.customer, customer)
        self.assertEqual(invoice.customer_display, "Ajay New")

    def test_name_only_walk_in_snapshot(self):
        response = self._post(create_customer="")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Customer.objects.exists())
        invoice = Invoice.objects.get()
        self.assertIsNone(invoice.customer)
        self.assertEqual(invoice.customer_name, "Ajay New")
        self.assertEqual(invoice.customer_display, "Ajay New")
        self.assertEqual(invoice.cash_entry.party_name, "Ajay New")

    def test_customer_and_name_together_rejected(self):
        customer = Customer.objects.create(full_name="Existing")
        response = self._post(customer=str(customer.pk), create_customer="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())

    def test_create_customer_requires_name(self):
        response = self._post(customer_name="", create_customer="on")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_no_permission_saves_name_only(self):
        self.client.logout()
        counter = User.objects.create_user(username="counter", password="StrongPass#123")
        assign_role_group(counter, Role.COUNTER_STAFF)
        self.client.login(username="counter", password="StrongPass#123")
        response = self._post(create_customer="on")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Customer.objects.exists())
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.customer_name, "Ajay New")
        self.assertIsNone(invoice.customer)

    def test_credit_bill_still_requires_registered_customer(self):
        response = self._post(payment_mode="CREDIT", create_customer="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())

    def test_credit_bill_works_with_quick_created_customer(self):
        Customer.objects.create(full_name="Ajay New", credit_limit=500)
        customer = Customer.objects.get(full_name="Ajay New")
        response = self._post(
            payment_mode="CREDIT",
            customer=str(customer.pk),
            create_customer="",
            customer_name="",
        )
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.status, "UNPAID")
