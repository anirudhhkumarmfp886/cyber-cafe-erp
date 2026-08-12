"""Tests for the work entry service layer (draft + finalize ledger booking)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.services.customer_service import CustomerService
from apps.employees.models import Role, WalletType
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import BankTransaction, CashBookEntry
from apps.finance.models.enums import BankTransactionCategory, CashEntryCategory
from apps.finance.services.bank_service import BankService
from apps.services.services.service_service import ServiceService
from apps.workentry.models import WorkEntry, WorkEntryStatus, WorkPaymentMode
from apps.workentry.services.workentry_service import WorkEntryService

User = get_user_model()


class WorkEntryServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username="we-owner", password="OwnerPass#123")
        self.staff = EmployeeService.create_employee(
            data={
                "username": "we-staff",
                "password": "StrongPass#123",
                "full_name": "Counter Staff",
                "role": Role.COUNTER_STAFF,
            },
            by=self.owner,
        )
        self.service = ServiceService.create_service(
            data={"name": "Printing B/W", "price": 20}, by=self.owner
        )
        self.account = BankService.create_account(
            account_name="HDFC Main", bank_name="HDFC", account_number="9001", by=self.owner
        )
        self.customer = CustomerService.create_customer(
            data={"full_name": "Rahul", "phone": "9999000001", "credit_limit": 1000},
            by=self.owner,
        )

    def _draft(self, **overrides):
        data = {
            "service": self.service,
            "charged_amount": 20,
            "payment_mode": WorkPaymentMode.CASH,
            "entry_date": None,
            "page_quantity": 5,
        }
        data.update(overrides)
        return WorkEntryService.create_draft(data=data, by=self.staff.user)

    def _cash_wallet(self):
        return WalletService.get_or_create_wallet(self.staff, WalletType.CASH)

    def _online_wallet(self):
        return WalletService.get_or_create_wallet(self.staff, WalletType.ONLINE)

    def test_create_draft_mints_reference_and_staff(self):
        entry = self._draft()
        self.assertEqual(entry.status, WorkEntryStatus.DRAFT)
        self.assertTrue(entry.reference_number.startswith("WE-"))
        self.assertEqual(entry.employee, self.staff)
        from datetime import date

        self.assertIsInstance(entry.entry_date, date)

    def test_create_draft_requires_employee_login(self):
        stranger = User.objects.create_user(username="we-stranger", password="Pass#123")
        with self.assertRaisesMessage(ValueError, "Only employees"):
            WorkEntryService.create_draft(data={"service": self.service, "charged_amount": 10}, by=stranger)

    def test_create_draft_requires_total(self):
        with self.assertRaisesMessage(ValueError, "at least one amount"):
            self._draft(charged_amount=0, transfer_to_customer=0)

    def test_finalize_cash_books_wallet_and_income(self):
        entry = self._draft(charged_amount=20, cash_withdrawal=500)
        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        entry.refresh_from_db()

        self.assertEqual(entry.status, WorkEntryStatus.SAVED)
        self.assertEqual(entry.income, Decimal("20"))
        self.assertEqual(entry.total, Decimal("520"))
        # Cash float: collected 520, gave back 500 -> net +20.
        self.assertEqual(WalletService.balance_of(self._cash_wallet()), Decimal("20"))
        # Income = charged only.
        income = CashBookEntry.objects.get(category=CashEntryCategory.SALES)
        self.assertEqual(income.amount, Decimal("20"))
        # No CASH_OUT expense for the pass-through leg.
        self.assertFalse(CashBookEntry.objects.filter(category=CashEntryCategory.CASH_OUT).exists())
        # The withdrawal leg is a staff CASH wallet debit only.
        self.assertTrue(
            WalletService.balance_of(self._cash_wallet()) == Decimal("20")
        )
        self.assertEqual(
            entry._meta.get_field("total").value_from_object(entry), Decimal("520")
        )

    def test_finalize_cash_simple_income_only(self):
        entry = self._draft(charged_amount=100)
        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        entry.refresh_from_db()
        self.assertEqual(WalletService.balance_of(self._cash_wallet()), Decimal("100"))
        self.assertEqual(CashBookEntry.objects.get(category=CashEntryCategory.SALES).amount, Decimal("100"))

    def test_finalize_upi_deposits_bank_and_credits_online_wallet(self):
        entry = self._draft(
            charged_amount=20,
            payment_mode=WorkPaymentMode.UPI,
            bank_account=self.account,
            transfer_to_customer=200,
            transfer_on_behalf=200,
        )
        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        entry.refresh_from_db()

        self.assertEqual(entry.total, Decimal("420"))
        txn = BankTransaction.objects.get(category=BankTransactionCategory.PAYMENT_RECEIVED)
        self.assertEqual(txn.amount, Decimal("420"))
        self.assertEqual(txn.account, self.account)
        # Online float: collected 420, paid out 400 -> net +20.
        self.assertEqual(WalletService.balance_of(self._online_wallet()), Decimal("20"))
        self.assertEqual(CashBookEntry.objects.get(category=CashEntryCategory.SALES).amount, Decimal("20"))

    def test_finalize_upi_requires_bank_account(self):
        entry = self._draft(charged_amount=20, payment_mode=WorkPaymentMode.UPI)
        with self.assertRaisesMessage(ValueError, "bank account"):
            WorkEntryService.finalize(entry=entry, by=self.staff.user)

    def test_finalize_customer_credit_settles_balance_first(self):
        CustomerService.adjust_credit(customer=self.customer, amount=300, by=self.owner)
        entry = self._draft(
            charged_amount=100,
            payment_mode=WorkPaymentMode.CUSTOMER_CREDIT,
            customer=self.customer,
            credit_rest_mode=WorkPaymentMode.CASH,
        )
        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        entry.refresh_from_db()
        self.customer.refresh_from_db()

        self.assertEqual(entry.credit_used, Decimal("100"))
        self.assertEqual(self.customer.credit_balance, Decimal("200"))
        # Rest was zero, so nothing extra collected into the cash wallet.
        self.assertEqual(WalletService.balance_of(self._cash_wallet()), Decimal("0"))
        # Income still charged amount.
        self.assertEqual(CashBookEntry.objects.get(category=CashEntryCategory.SALES).amount, Decimal("100"))

    def test_finalize_customer_credit_collects_rest(self):
        CustomerService.adjust_credit(customer=self.customer, amount=50, by=self.owner)
        entry = self._draft(
            charged_amount=100,
            payment_mode=WorkPaymentMode.CUSTOMER_CREDIT,
            customer=self.customer,
            credit_rest_mode=WorkPaymentMode.CASH,
        )
        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        entry.refresh_from_db()

        self.assertEqual(entry.credit_used, Decimal("50"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.credit_balance, Decimal("0"))
        # Rest 50 collected in cash.
        self.assertEqual(WalletService.balance_of(self._cash_wallet()), Decimal("50"))

    def test_finalize_customer_credit_requires_customer(self):
        entry = self._draft(
            charged_amount=100, payment_mode=WorkPaymentMode.CUSTOMER_CREDIT
        )
        with self.assertRaisesMessage(ValueError, "requires a customer"):
            WorkEntryService.finalize(entry=entry, by=self.staff.user)

    def test_finalize_customer_credit_requires_rest_mode_when_unpaid(self):
        CustomerService.adjust_credit(customer=self.customer, amount=50, by=self.owner)
        entry = self._draft(
            charged_amount=100,
            payment_mode=WorkPaymentMode.CUSTOMER_CREDIT,
            customer=self.customer,
            credit_rest_mode="",
        )
        with self.assertRaisesMessage(ValueError, "rest"):
            WorkEntryService.finalize(entry=entry, by=self.staff.user)

    def test_finalize_rejects_negative_amounts(self):
        entry = WorkEntry.objects.create(
            employee=self.staff,
            service=self.service,
            charged_amount=Decimal("-5"),
            payment_mode=WorkPaymentMode.CASH,
            created_by=self.staff.user,
            updated_by=self.staff.user,
        )
        with self.assertRaisesMessage(ValueError, "negative"):
            WorkEntryService.finalize(entry=entry, by=self.staff.user)

    def test_finalize_cannot_run_twice(self):
        entry = self._draft(charged_amount=50)
        WorkEntryService.finalize(entry=entry, by=self.staff.user)
        with self.assertRaisesMessage(ValueError, "already saved"):
            WorkEntryService.finalize(entry=entry, by=self.staff.user)

    def test_finalize_is_atomic_on_wallet_failure(self):
        # UPI mode with a cash-withdrawal leg: the bank deposit and the ONLINE
        # wallet credit land first, then the CASH wallet debit fails (no cash
        # float). The whole transaction must roll back — nothing may leak.
        entry = self._draft(
            charged_amount=20,
            payment_mode=WorkPaymentMode.UPI,
            bank_account=self.account,
            cash_withdrawal=500,
        )
        with self.assertRaisesMessage(ValueError, "Insufficient wallet balance"):
            WorkEntryService.finalize(entry=entry, by=self.staff.user)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WorkEntryStatus.DRAFT)
        self.assertFalse(CashBookEntry.objects.filter(category=CashEntryCategory.SALES).exists())
        self.assertFalse(BankTransaction.objects.exists())
        self.assertEqual(WalletService.balance_of(self._online_wallet()), Decimal("0"))
        self.assertEqual(WalletService.balance_of(self._cash_wallet()), Decimal("0"))
