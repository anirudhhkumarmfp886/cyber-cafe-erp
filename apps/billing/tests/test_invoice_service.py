"""Tests for the billing service layer (invoices, settlements, voids)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.billing.models import Invoice, InvoiceStatus
from apps.billing.services.billing_service import BillingService
from apps.customers.services.customer_service import CustomerService
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import BankAccount, CashBookEntry, UPIBookEntry
from apps.finance.models.enums import CashEntryCategory, CashEntryType
from apps.services.services.service_service import ServiceService

User = get_user_model()


class BillingServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cashier", password="Pass#123")
        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "category": "GAMES", "price": 40}, by=self.user
        )
        self.printing = ServiceService.create_service(
            data={"name": "Printing B/W", "category": "PRINTING", "price": 2}, by=self.user
        )
        self.customer = CustomerService.create_customer(
            data={"full_name": "Rahul Sharma", "phone": "9999000001", "credit_limit": 500},
            by=self.user,
        )

    def _bill(self, lines, **kwargs):
        data = {"customer": kwargs.get("customer"), "payment_mode": kwargs.get("payment_mode", "CASH"), "discount": kwargs.get("discount", 0)}
        return BillingService.create_invoice(data=data, lines=lines, by=self.user)

    def test_cash_invoice_derives_totals_and_books_income(self):
        invoice = self._bill([(self.gaming, 2), (self.printing, 3)])
        self.assertEqual(invoice.subtotal, 86)
        self.assertEqual(invoice.total, 86)
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.invoice_number[:4], "INV-")
        self.assertEqual(invoice.lines.count(), 2)
        income = CashBookEntry.objects.get(category=CashEntryCategory.SALES)
        self.assertEqual(income.entry_type, CashEntryType.INCOME)
        self.assertEqual(income.amount, 86)

    def test_discount_reduces_total(self):
        invoice = self._bill([(self.gaming, 2)], discount=10)
        self.assertEqual(invoice.subtotal, 80)
        self.assertEqual(invoice.discount, 10)
        self.assertEqual(invoice.total, 70)

    def test_invoice_requires_at_least_one_line(self):
        with self.assertRaisesMessage(ValueError, "at least one line"):
            BillingService.create_invoice(data={"payment_mode": "CASH"}, lines=[], by=self.user)

    def test_zero_quantity_rejected(self):
        with self.assertRaisesMessage(ValueError, "greater than zero"):
            self._bill([(self.gaming, 0)])

    def test_inactive_service_cannot_be_billed(self):
        ServiceService.deactivate_service(self.printing, by=self.user)
        with self.assertRaisesMessage(ValueError, "inactive"):
            self._bill([(self.printing, 1)])

    def test_discount_cannot_exceed_subtotal(self):
        with self.assertRaisesMessage(ValueError, "cannot exceed"):
            self._bill([(self.gaming, 1)], discount=100)

    def test_credit_invoice_requires_customer(self):
        with self.assertRaisesMessage(ValueError, "requires a customer"):
            self._bill([(self.gaming, 1)], payment_mode="CREDIT")

    def test_credit_invoice_respects_credit_limit(self):
        invoice = self._bill([(self.gaming, 2)], payment_mode="CREDIT", customer=self.customer)
        self.assertEqual(invoice.status, InvoiceStatus.UNPAID)
        self.assertEqual(invoice.outstanding_amount, 80)
        self.assertFalse(CashBookEntry.objects.filter(category=CashEntryCategory.SALES).exists())

        with self.assertRaisesMessage(ValueError, "Credit limit exceeded"):
            self._bill([(self.gaming, 11)], payment_mode="CREDIT", customer=self.customer)

    def test_customer_without_credit_limit_cannot_use_credit(self):
        walk_in = CustomerService.create_customer(
            data={"full_name": "No Limit", "phone": "9999000002"}, by=self.user
        )
        with self.assertRaisesMessage(ValueError, "no credit limit"):
            self._bill([(self.gaming, 1)], payment_mode="CREDIT", customer=walk_in)

    def test_settle_partial_then_full(self):
        invoice = self._bill([(self.gaming, 2)], payment_mode="CREDIT", customer=self.customer)
        BillingService.settle_invoice(invoice=invoice, amount=30, payment_mode="UPI", by=self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PARTIAL)
        self.assertEqual(invoice.outstanding_amount, 50)
        # UPI settlement goes to UPI Book, NOT Cash Book
        self.assertEqual(UPIBookEntry.objects.filter(category=CashEntryCategory.SALES).count(), 1)
        self.assertEqual(CashBookEntry.objects.filter(category=CashEntryCategory.SALES).count(), 0)

        BillingService.settle_invoice(invoice=invoice, amount=50, payment_mode="CASH", by=self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.outstanding_amount, 0)
        # Cash settlement adds 1 entry to Cash Book
        self.assertEqual(CashBookEntry.objects.filter(category=CashEntryCategory.SALES).count(), 1)

    def test_settle_cannot_exceed_outstanding(self):
        invoice = self._bill([(self.gaming, 1)], payment_mode="CREDIT", customer=self.customer)
        with self.assertRaisesMessage(ValueError, "exceeds the outstanding"):
            BillingService.settle_invoice(invoice=invoice, amount=81, payment_mode="CASH", by=self.user)

    def test_settle_paid_invoice_rejected(self):
        invoice = self._bill([(self.gaming, 1)])
        with self.assertRaisesMessage(ValueError, "already fully paid"):
            BillingService.settle_invoice(invoice=invoice, amount=10, payment_mode="CASH", by=self.user)

    def test_void_reverses_linked_cash_entries(self):
        invoice = self._bill([(self.gaming, 1)])
        entry = invoice.cash_entry
        self.assertTrue(entry.is_active)
        BillingService.soft_delete_invoice(invoice=invoice, by=self.user)
        self.assertFalse(Invoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(Invoice.all_objects.filter(pk=invoice.pk).exists())
        entry.refresh_from_db()
        self.assertFalse(entry.is_active)

    def test_void_credit_invoice_reverses_settlement_entries(self):
        invoice = self._bill([(self.gaming, 2)], payment_mode="CREDIT", customer=self.customer)
        BillingService.settle_invoice(invoice=invoice, amount=80, payment_mode="CASH", by=self.user)
        entries = [p.cash_entry for p in invoice.payments.all()]
        BillingService.soft_delete_invoice(invoice=invoice, by=self.user)
        for entry in entries:
            entry.refresh_from_db()
            self.assertFalse(entry.is_active)


class PaymentDestinationRoutingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="staff1", password="Pass#123")
        from apps.employees.models import Employee, Role
        self.employee = Employee.objects.create(
            user=self.user,
            employee_code="EMP-TEST-001",
            full_name="Staff Member",
            role=Role.COUNTER_STAFF,
        )
        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "category": "GAMES", "price": 100}, by=self.user
        )
        self.bank = BankAccount.objects.create(
            account_name="Shop HDFC",
            account_number="1234567890",
            bank_name="HDFC",
            is_default=True,
        )

    def test_auto_destination_routes_cash_to_staff_and_upi_to_shop(self):
        from apps.employees.models import WalletType
        from apps.billing.models import PaymentDestination

        # AUTO Cash
        inv_cash = BillingService.create_invoice(
            data={"payment_mode": "CASH", "payment_destination": PaymentDestination.AUTO},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.user,
        )
        p_cash = inv_cash.payments.first()
        self.assertEqual(p_cash.payment_destination, PaymentDestination.STAFF)
        cash_wallet = WalletService.get_or_create_wallet(self.employee, WalletType.CASH)
        self.assertEqual(cash_wallet.balance, 100)

        # AUTO UPI
        inv_upi = BillingService.create_invoice(
            data={"payment_mode": "UPI", "payment_destination": PaymentDestination.AUTO},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.user,
        )
        p_upi = inv_upi.payments.first()
        self.assertEqual(p_upi.payment_destination, PaymentDestination.SHOP)
        self.assertEqual(p_upi.bank_account, self.bank)
        self.assertEqual(self.bank.balance, 100)

    def test_staff_destination_routes_both_cash_and_upi_to_staff(self):
        from apps.employees.models import WalletType
        from apps.billing.models import PaymentDestination

        # STAFF Cash
        inv_cash = BillingService.create_invoice(
            data={"payment_mode": "CASH", "payment_destination": PaymentDestination.STAFF},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.user,
        )
        p_cash = inv_cash.payments.first()
        self.assertEqual(p_cash.payment_destination, PaymentDestination.STAFF)
        cash_wallet = WalletService.get_or_create_wallet(self.employee, WalletType.CASH)
        self.assertEqual(cash_wallet.balance, 100)

        # STAFF UPI
        inv_upi = BillingService.create_invoice(
            data={"payment_mode": "UPI", "payment_destination": PaymentDestination.STAFF},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.user,
        )
        p_upi = inv_upi.payments.first()
        self.assertEqual(p_upi.payment_destination, PaymentDestination.STAFF)
        online_wallet = WalletService.get_or_create_wallet(self.employee, WalletType.ONLINE)
        self.assertEqual(online_wallet.balance, 100)

    def test_shop_destination_routes_both_cash_and_upi_to_shop(self):
        from apps.employees.models import WalletType
        from apps.billing.models import PaymentDestination

        # SHOP Cash (Direct Galla)
        inv_cash = BillingService.create_invoice(
            data={"payment_mode": "CASH", "payment_destination": PaymentDestination.SHOP},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.user,
        )
        p_cash = inv_cash.payments.first()
        self.assertEqual(p_cash.payment_destination, PaymentDestination.SHOP)
        cash_wallet = WalletService.get_or_create_wallet(self.employee, WalletType.CASH)
        self.assertEqual(cash_wallet.balance, 0)

        # SHOP UPI
        inv_upi = BillingService.create_invoice(
            data={"payment_mode": "UPI", "payment_destination": PaymentDestination.SHOP},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.user,
        )
        p_upi = inv_upi.payments.first()
        self.assertEqual(p_upi.payment_destination, PaymentDestination.SHOP)
        self.assertEqual(p_upi.bank_account, self.bank)
        self.assertEqual(self.bank.balance, 100)

