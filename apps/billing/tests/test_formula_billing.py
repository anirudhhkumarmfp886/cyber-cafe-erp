"""Sprint 4.5 tests: formula-driven pricing, customer-wallet payments, void refunds."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import InvoiceStatus
from apps.billing.services.billing_service import BillingService
from apps.customers.services.customer_service import CustomerService
from apps.employees.models import Role, WalletType
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import CashBookEntry
from apps.finance.models.enums import CashEntryCategory
from apps.finance.services.bank_service import BankService
from apps.services.services.service_service import ServiceService

User = get_user_model()


class FormulaBillingServiceTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = User.objects.create_superuser(username="fb-owner", password="OwnerPass#123")
        self.manager = EmployeeService.create_employee(
            data={
                "username": "fb-manager",
                "password": "StrongPass#123",
                "full_name": "FB Manager",
                "role": Role.MANAGER,
            },
            by=self.owner,
        ).user
        self.customer = CustomerService.create_customer(
            data={"full_name": "Formula Customer", "phone": "9999000098", "credit_limit": 500},
            by=self.owner,
        )
        self.account = BankService.create_account(
            account_name="HDFC Main", bank_name="HDFC", account_number="601", by=self.owner
        )

    def _top_up_online(self, amount=2000):
        BankService.deposit(account=self.account, amount=amount, party_name="Owner", by=self.owner)
        WalletService.top_up(
            employee=self.manager.employee,
            wallet_type=WalletType.ONLINE,
            amount=amount,
            bank_account=self.account,
            by=self.owner,
        )

    def _formula_service(self, name="Money Transfer", total="cash + pct", income="cash * pct / 100", passthrough_type="ONLINE"):
        service = ServiceService.create_service(
            data={
                "name": name,
                "new_category": "Transfers",
                "price": 10,
                "passthrough_type": passthrough_type,
                "total_formula": total,
                "income_formula": income,
            },
            by=self.owner,
        )
        cash = ServiceService.create_custom_field(
            service,
            data={"label": "Cash", "variable_name": "cash", "field_type": "NUMBER", "required": True},
            by=self.owner,
        )
        pct = ServiceService.create_custom_field(
            service,
            data={"label": "Commission Percent", "variable_name": "pct", "field_type": "PERCENT", "required": True},
            by=self.owner,
        )
        return service, cash, pct

    def test_formula_line_income_differs_from_amount(self):
        self._top_up_online()
        service, cash, pct = self._formula_service()
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH", "discount": 0},
            lines=[{"service": service, "qty": 1, "custom": {str(cash.pk): "1000", str(pct.pk): "2"}}],
            by=self.manager,
        )
        line = invoice.lines.get()
        self.assertEqual(line.amount, Decimal("1002.00"))  # cash + pct
        self.assertEqual(line.income_amount, Decimal("20.00"))  # 2% of 1000
        self.assertEqual(invoice.income_amount, Decimal("20.00"))
        self.assertEqual(invoice.pass_through_amount, Decimal("982.00"))

    def test_plain_sale_income_equals_amount(self):
        service = ServiceService.create_service(data={"name": "Print", "price": 5}, by=self.owner)
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH", "discount": 0},
            lines=[{"service": service, "qty": 3}],
            by=self.manager,
        )
        line = invoice.lines.get()
        self.assertEqual(line.amount, Decimal("15.00"))
        self.assertEqual(line.income_amount, Decimal("15.00"))

    def test_income_formula_cannot_exceed_total(self):
        service, cash, pct = self._formula_service(name="Bad", income="cash * 2")
        with self.assertRaisesMessage(ValueError, "cannot exceed the charged amount"):
            BillingService.create_invoice(
                data={"payment_mode": "CASH", "discount": 0},
                lines=[{"service": service, "qty": 1, "custom": {str(cash.pk): "100", str(pct.pk): "1"}}],
                by=self.manager,
            )

    def test_unknown_variable_in_formula_rejected(self):
        service = ServiceService.create_service(
            data={
                "name": "Bad Formula",
                "price": 10,
                "total_formula": "typo + 1",
            },
            by=self.owner,
        )
        with self.assertRaisesMessage(ValueError, "unknown variable 'typo'"):
            BillingService.create_invoice(
                data={"payment_mode": "CASH", "discount": 0},
                lines=[{"service": service, "qty": 1}],
                by=self.manager,
            )

    def test_passthrough_books_online_wallet_debit(self):
        self._top_up_online()
        service, cash, pct = self._formula_service()
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH", "discount": 0},
            lines=[{"service": service, "qty": 1, "custom": {str(cash.pk): "1000", str(pct.pk): "2"}}],
            by=self.manager,
        )
        line = invoice.lines.get()
        wallet_entry = line.wallet_entry
        self.assertIsNotNone(wallet_entry)
        self.assertEqual(wallet_entry.amount, Decimal("982.00"))
        self.assertFalse(CashBookEntry.objects.filter(category=CashEntryCategory.CASH_OUT).exists())
        self.assertEqual(
            WalletService.balance_of_employee(self.manager.employee, WalletType.ONLINE),
            Decimal("2000") - Decimal("982"),
        )

    def test_cash_passthrough_books_cash_out(self):
        WalletService.top_up(
            employee=self.manager.employee,
            wallet_type=WalletType.CASH,
            amount=5000,
            by=self.owner,
        )
        service, cash, pct = self._formula_service(
            name="Withdrawal", passthrough_type="CASH"
        )
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH", "discount": 0},
            lines=[{"service": service, "qty": 1, "custom": {str(cash.pk): "1000", str(pct.pk): "2"}}],
            by=self.manager,
        )
        line = invoice.lines.get()
        wallet_entry = line.wallet_entry
        self.assertIsNotNone(wallet_entry)
        self.assertEqual(wallet_entry.amount, Decimal("982.00"))
        self.assertTrue(CashBookEntry.objects.filter(category=CashEntryCategory.CASH_OUT).exists())


class CustomerWalletPaymentTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = User.objects.create_superuser(username="wallet-owner", password="OwnerPass#123")
        self.manager = EmployeeService.create_employee(
            data={
                "username": "wallet-manager",
                "password": "StrongPass#123",
                "full_name": "Wallet Manager",
                "role": Role.MANAGER,
            },
            by=self.owner,
        ).user
        self.customer = CustomerService.create_customer(
            data={"full_name": "Wallet Customer", "phone": "9999000097", "credit_limit": 1000},
            by=self.owner,
        )
        self.customer.credit_balance = Decimal("500.00")
        self.customer.save(update_fields=["credit_balance"])
        self.gaming = ServiceService.create_service(data={"name": "Gaming", "price": 100}, by=self.owner)

    def _wallet_bill(self, qty=1):
        return BillingService.create_invoice(
            data={"payment_mode": "CUSTOMER_WALLET", "discount": 0, "customer": self.customer},
            lines=[{"service": self.gaming, "qty": qty}],
            by=self.manager,
        )

    def test_wallet_payment_draws_down_credit_balance(self):
        invoice = self._wallet_bill()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        payment = invoice.payments.get()
        self.assertEqual(payment.payment_mode, "CUSTOMER_WALLET")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.credit_balance, Decimal("400.00"))
        self.assertFalse(CashBookEntry.objects.exists())

    def test_wallet_payment_insufficient_balance_rejected(self):
        self.customer.credit_balance = Decimal("50.00")
        self.customer.save(update_fields=["credit_balance"])
        with self.assertRaisesMessage(ValueError, "Insufficient customer credit balance"):
            self._wallet_bill(qty=2)

    def test_wallet_payment_without_customer_rejected(self):
        with self.assertRaisesMessage(ValueError, "require a customer"):
            BillingService.create_invoice(
                data={"payment_mode": "CUSTOMER_WALLET", "discount": 0},
                lines=[{"service": self.gaming, "qty": 1}],
                by=self.manager,
            )

    def test_settle_invoice_with_wallet(self):
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CREDIT", "discount": 0, "customer": self.customer},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.manager,
        )
        self.assertEqual(invoice.status, InvoiceStatus.UNPAID)
        BillingService.settle_invoice(
            invoice=invoice,
            amount=Decimal("100.00"),
            payment_mode="CUSTOMER_WALLET",
            by=self.manager,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.credit_balance, Decimal("400.00"))

    def test_void_invoice_refunds_wallet_payment(self):
        invoice = self._wallet_bill()
        BillingService.soft_delete_invoice(invoice=invoice, by=self.owner)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.credit_balance, Decimal("500.00"))
        self.assertFalse(invoice.is_active)

    def test_void_cash_invoice_removes_cash_entry(self):
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH", "discount": 0},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.manager,
        )
        entry_id = invoice.cash_entry_id
        self.assertTrue(CashBookEntry.objects.filter(id=entry_id, is_active=True).exists())
        BillingService.soft_delete_invoice(invoice=invoice, by=self.owner)
        self.assertFalse(CashBookEntry.objects.filter(id=entry_id, is_active=True).exists())
