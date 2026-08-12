"""Tests for split-payment billing and the cash-withdrawal auto-ledger."""
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
from apps.finance.models import BankTransaction, CashBookEntry
from apps.finance.models.enums import BankTransactionCategory, CashEntryCategory
from apps.finance.services.bank_service import BankService
from apps.services.services.service_service import ServiceService

User = get_user_model()


class SplitPaymentTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = User.objects.create_superuser(username="sp-owner", password="OwnerPass#123")
        self.staff = EmployeeService.create_employee(
            data={
                "username": "sp-staff",
                "password": "StrongPass#123",
                "full_name": "Split Staff",
                "role": Role.STAFF,
            },
            by=self.owner,
        ).user
        self.employee = self.staff.employee
        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "price": 300}, by=self.owner
        )
        self.account = BankService.create_account(
            account_name="HDFC Main", bank_name="HDFC", account_number="777", by=self.owner
        )
        self.customer = CustomerService.create_customer(
            data={"full_name": "Split Customer", "phone": "9999000099", "credit_limit": 1000},
            by=self.owner,
        )

    def _withdrawal_service(self):
        service = ServiceService.create_service(
            data={"name": "Cash Withdrawal", "price": 50}, by=self.owner
        )
        transfer = ServiceService.create_custom_field(
            service,
            data={"label": "Transfer", "field_type": "BANK_TRANSFER", "required": True},
            by=self.owner,
        )
        percent = ServiceService.create_custom_field(
            service,
            data={"label": "Commission", "field_type": "PERCENT"},
            by=self.owner,
        )
        bank = ServiceService.create_custom_field(
            service,
            data={"label": "Bank Account", "field_type": "BANK_ACCOUNT", "required": True},
            by=self.owner,
        )
        custom = {
            str(transfer.pk): "1040",
            str(percent.pk): "4",
            str(bank.pk): str(self.account.pk),
        }
        return service, custom

    def test_full_withdrawal_scenario(self):
        service, custom = self._withdrawal_service()
        WalletService.top_up(
            employee=self.employee, wallet_type=WalletType.CASH, amount=1000, by=self.owner
        )
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH"},
            lines=[
                {"service": service, "qty": 1, "custom": custom},
                {"service": self.gaming, "qty": 1},
            ],
            payments=[
                {"mode": "CASH", "amount": "40", "bank_account": None},
                {"mode": "UPI", "amount": "1300", "bank_account": self.account},
            ],
            by=self.staff,
        )
        self.assertEqual(invoice.total, Decimal("1340"))
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.payments.count(), 2)

        withdrawal_line = invoice.lines.get(service=service)
        self.assertEqual(withdrawal_line.amount, Decimal("1040"))
        self.assertEqual(withdrawal_line.withdrawal_summary, "1000 + 4% = 1040")

        # staff CASH wallet: +1000 float, -1000 handed out, +40 cash collected
        self.assertEqual(
            WalletService.balance_of_employee(self.employee, WalletType.CASH), Decimal("40")
        )
        # staff ONLINE wallet: the full UPI leg
        self.assertEqual(
            WalletService.balance_of_employee(self.employee, WalletType.ONLINE), Decimal("1300")
        )

        deposits = BankTransaction.objects.filter(
            account=self.account, category=BankTransactionCategory.PAYMENT_RECEIVED
        )
        self.assertEqual(deposits.count(), 1)
        self.assertEqual(deposits.first().amount, Decimal("1300"))

        # Cash book: only the cash leg is income here (UPI lives in the bank);
        # commission is booked, and the cash handed out is the matching expense.
        self.assertEqual(
            CashBookEntry.objects.get(category=CashEntryCategory.SALES).amount, Decimal("40")
        )
        self.assertEqual(
            CashBookEntry.objects.get(category=CashEntryCategory.COMMISSION).amount, Decimal("40")
        )
        self.assertEqual(
            CashBookEntry.objects.get(category=CashEntryCategory.CASH_OUT).amount, Decimal("1000")
        )

    def test_withdrawal_line_supplies_bank_for_upi_payment(self):
        service, custom = self._withdrawal_service()
        WalletService.top_up(
            employee=self.employee, wallet_type=WalletType.CASH, amount=2000, by=self.owner
        )
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH"},
            lines=[{"service": service, "qty": 1, "custom": custom}],
            payments=[{"mode": "UPI", "amount": "1040", "bank_account": None}],
            by=self.staff,
        )
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(
            BankTransaction.objects.get(
                category=BankTransactionCategory.PAYMENT_RECEIVED
            ).amount,
            Decimal("1040"),
        )
        self.assertEqual(invoice.payments.get().bank_account, self.account)

    def test_split_payment_books_both_ledgers(self):
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH"},
            lines=[{"service": self.gaming, "qty": 1}],
            payments=[
                {"mode": "CASH", "amount": "100", "bank_account": None},
                {"mode": "UPI", "amount": "200", "bank_account": self.account},
            ],
            by=self.staff,
        )
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.payments.count(), 2)
        self.assertEqual(
            WalletService.balance_of_employee(self.employee, WalletType.CASH), Decimal("100")
        )
        self.assertEqual(
            WalletService.balance_of_employee(self.employee, WalletType.ONLINE), Decimal("200")
        )
        self.assertEqual(
            BankTransaction.objects.get(
                category=BankTransactionCategory.PAYMENT_RECEIVED
            ).amount,
            Decimal("200"),
        )
        self.assertEqual(
            CashBookEntry.objects.get(category=CashEntryCategory.SALES).amount, Decimal("100")
        )

    def test_payments_exceeding_total_rejected(self):
        with self.assertRaisesMessage(ValueError, "exceeds the bill total"):
            BillingService.create_invoice(
                data={"payment_mode": "CASH"},
                lines=[{"service": self.gaming, "qty": 1}],
                payments=[
                    {"mode": "CASH", "amount": "200", "bank_account": None},
                    {"mode": "UPI", "amount": "200", "bank_account": self.account},
                ],
                by=self.staff,
            )

    def test_upi_payment_requires_bank_account(self):
        with self.assertRaisesMessage(ValueError, "need a shop bank account"):
            BillingService.create_invoice(
                data={"payment_mode": "UPI"},
                lines=[{"service": self.gaming, "qty": 1}],
                payments=[{"mode": "UPI", "amount": "300", "bank_account": None}],
                by=self.staff,
            )

    def test_partial_payment_requires_customer(self):
        with self.assertRaisesMessage(ValueError, "partial payment requires a customer"):
            BillingService.create_invoice(
                data={"payment_mode": "CASH"},
                lines=[{"service": self.gaming, "qty": 1}],
                payments=[{"mode": "CASH", "amount": "100", "bank_account": None}],
                by=self.staff,
            )
        invoice = BillingService.create_invoice(
            data={"customer": self.customer, "payment_mode": "CASH"},
            lines=[{"service": self.gaming, "qty": 1}],
            payments=[{"mode": "CASH", "amount": "100", "bank_account": None}],
            by=self.staff,
        )
        self.assertEqual(invoice.status, InvoiceStatus.PARTIAL)
        self.assertEqual(invoice.outstanding_amount, Decimal("200"))

    def test_legacy_single_payment_still_books_cash_entry(self):
        invoice = BillingService.create_invoice(
            data={"payment_mode": "CASH"},
            lines=[{"service": self.gaming, "qty": 1}],
            by=self.staff,
        )
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertIsNotNone(invoice.cash_entry)
        self.assertEqual(invoice.payments.count(), 1)
        self.assertEqual(invoice.payments.get().cash_entry_id, invoice.cash_entry_id)
        self.assertEqual(
            WalletService.balance_of_employee(self.employee, WalletType.CASH), Decimal("300")
        )

    def test_void_reverses_bank_deposit(self):
        invoice = BillingService.create_invoice(
            data={"payment_mode": "UPI"},
            lines=[{"service": self.gaming, "qty": 1}],
            payments=[{"mode": "UPI", "amount": "300", "bank_account": self.account}],
            by=self.staff,
        )
        deposit = BankTransaction.objects.get(
            category=BankTransactionCategory.PAYMENT_RECEIVED
        )
        self.assertTrue(deposit.is_active)
        BillingService.soft_delete_invoice(invoice=invoice, by=self.owner)
        deposit.refresh_from_db()
        self.assertFalse(deposit.is_active)
