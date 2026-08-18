"""Tests for billing views + permission enforcement."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.billing.forms.invoice import InvoiceLineFormSet
from apps.billing.models import Invoice
from apps.billing.services.billing_service import BillingService
from apps.customers.services.customer_service import CustomerService
from apps.services.services.service_service import ServiceService

User = get_user_model()


def _line_formset_data(service_pk, qty, extra_lines=0):
    formset = InvoiceLineFormSet(instance=Invoice(), prefix="line")
    data = {
        f"{formset.prefix}-TOTAL_FORMS": str(1 + extra_lines),
        f"{formset.prefix}-INITIAL_FORMS": "0",
        f"{formset.prefix}-MIN_NUM_FORMS": "1",
        f"{formset.prefix}-MAX_NUM_FORMS": "1000",
        f"{formset.prefix}-0-service": str(service_pk),
        f"{formset.prefix}-0-qty": str(qty),
        f"{formset.prefix}-0-id": "",
    }
    for i in range(1, 1 + extra_lines):
        data[f"{formset.prefix}-{i}-service"] = ""
        data[f"{formset.prefix}-{i}-qty"] = ""
        data[f"{formset.prefix}-{i}-id"] = ""
    return data


class BillingViewTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.client.login(username="boss", password="OwnerPass#123")
        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "category": "GAMES", "price": 40}, by=self.boss
        )
        self.customer = CustomerService.create_customer(
            data={"full_name": "Rahul", "phone": "9999000001", "credit_limit": 500},
            by=self.boss,
        )

    def test_list_page_creates_cash_invoice(self):
        data = {
            "customer": "",
            "payment_mode": "CASH",
            "discount": "0",
            "notes": "walk-in",
        }
        data.update(_line_formset_data(self.gaming.pk, 2))
        response = self.client.post(reverse("billing:list"), data)
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.total, 80)
        self.assertEqual(invoice.status, "PAID")

    def test_list_page_creates_credit_invoice(self):
        data = {
            "customer": str(self.customer.pk),
            "payment_mode": "CREDIT",
            "discount": "0",
            "notes": "",
        }
        data.update(_line_formset_data(self.gaming.pk, 1))
        response = self.client.post(reverse("billing:list"), data)
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.status, "UNPAID")
        self.assertEqual(invoice.outstanding_amount, 40)

    def test_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("billing:list"))
        self.assertEqual(response.status_code, 302)

    def test_detail_shows_lines_and_renders(self):
        invoice = BillingService.create_invoice(
            data={"customer": self.customer, "payment_mode": "CREDIT"},
            lines=[(self.gaming, 2)],
            by=self.boss,
        )
        response = self.client.get(reverse("billing:detail", kwargs={"pk": invoice.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INV-")
        self.assertContains(response, "Gaming 1hr")

    def test_settle_via_web(self):
        invoice = BillingService.create_invoice(
            data={"customer": self.customer, "payment_mode": "CREDIT"},
            lines=[(self.gaming, 2)],
            by=self.boss,
        )
        response = self.client.post(
            reverse("billing:settle", kwargs={"pk": invoice.pk}),
            {"amount": "80", "payment_mode": "CASH", "notes": "full"},
        )
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "PAID")


class BillingPermissionTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        from apps.employees.models import Role
        from apps.employees.services.role_service import assign_role_group

        self.counter = User.objects.create_user(username="counter", password="StrongPass#123")
        self.staff = User.objects.create_user(username="staff", password="StrongPass#123")
        assign_role_group(self.counter, Role.COUNTER_STAFF)
        assign_role_group(self.staff, Role.STAFF)
        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "price": 40}, by=self.boss
        )

    def test_counter_staff_can_create_invoice(self):
        self.client.login(username="counter", password="StrongPass#123")
        data = {"customer": "", "payment_mode": "CASH", "discount": "0", "notes": ""}
        data.update(_line_formset_data(self.gaming.pk, 1))
        response = self.client.post(reverse("billing:list"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Invoice.objects.exists())

    def test_staff_cannot_create_invoice(self):
        self.client.login(username="staff", password="StrongPass#123")
        data = {"customer": "", "payment_mode": "CASH", "discount": "0", "notes": ""}
        data.update(_line_formset_data(self.gaming.pk, 1))
        response = self.client.post(reverse("billing:list"), data)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Invoice.objects.exists())
