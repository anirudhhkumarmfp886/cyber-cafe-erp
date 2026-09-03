"""Tests for NotificationService and Invoice Receipt View."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.common.services.notification_service import NotificationService
from apps.customers.models import Customer
from apps.inventory.models import StockItem
from apps.services.models import Service

User = get_user_model()


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="Pass#123", is_superuser=True)
        self.customer = Customer.objects.create(
            full_name="Rajesh Sharma",
            phone="9876543210",
        )
        self.service = Service.objects.create(name="Color Print", price=Decimal("10.00"))
        self.invoice = Invoice.objects.create(
            invoice_number="INV-000001",
            customer=self.customer,
            status=InvoiceStatus.PAID,
            payment_mode="CASH",
            total=Decimal("50.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            service=self.service,
            description="Color Print",
            qty=5,
            unit_price=Decimal("10.00"),
            amount=Decimal("50.00"),
            income_amount=Decimal("50.00"),
        )
        self.invoice.refresh_from_db()

    def test_phone_normalization(self):
        self.assertEqual(NotificationService.normalize_phone("9876543210"), "919876543210")
        self.assertEqual(NotificationService.normalize_phone("09876543210"), "919876543210")
        self.assertEqual(NotificationService.normalize_phone("919876543210"), "919876543210")
        self.assertEqual(NotificationService.normalize_phone("+91-98765-43210"), "919876543210")
        self.assertEqual(NotificationService.normalize_phone(""), "")

    def test_format_invoice_text(self):
        text = NotificationService.format_invoice_text(self.invoice)
        self.assertIn("INV-000001", text)
        self.assertIn("Rajesh Sharma", text)
        self.assertIn("Color Print x 5 — ₹50.00", text)
        self.assertIn("Total Amount:* ₹50.00", text)
        self.assertIn("PAID", text)

    def test_whatsapp_url_generation(self):
        url = NotificationService.get_invoice_whatsapp_url(self.invoice)
        self.assertTrue(url.startswith("https://wa.me/919876543210?text="))
        self.assertIn("INV-000001", url)

    def test_whatsapp_url_without_customer_phone(self):
        self.invoice.customer = None
        self.invoice.save()
        url = NotificationService.get_invoice_whatsapp_url(self.invoice)
        self.assertTrue(url.startswith("https://wa.me/?text="))

    def test_low_stock_summary(self):
        item = StockItem.objects.create(
            name="A4 Paper",
            current_stock=Decimal("2.00"),
            reorder_level=Decimal("5.00"),
        )
        msg = NotificationService.format_low_stock_summary([item])
        self.assertIn("Low Stock Alert", msg)
        self.assertIn("A4 Paper", msg)
        self.assertIn("Current: 2.00", msg)

    def test_low_stock_whatsapp_url(self):
        item = StockItem.objects.create(
            name="Toner",
            current_stock=Decimal("1.00"),
            reorder_level=Decimal("3.00"),
        )
        url = NotificationService.get_low_stock_whatsapp_url([item], owner_phone="9876543210")
        self.assertTrue(url.startswith("https://wa.me/919876543210?text="))
        self.assertIn("Toner", url)


class InvoiceReceiptViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="owner", password="Pass#123", is_superuser=True)
        self.client.login(username="owner", password="Pass#123")
        self.invoice = Invoice.objects.create(
            invoice_number="INV-000002",
            status=InvoiceStatus.PAID,
            payment_mode="UPI",
        )

    def test_receipt_page_loads(self):
        response = self.client.get(reverse("billing:receipt", kwargs={"pk": self.invoice.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INV-000002")
        self.assertContains(response, "Print Receipt")
        self.assertContains(response, "Share WhatsApp")
