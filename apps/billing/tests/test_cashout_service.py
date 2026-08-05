"""Tests for the cash-out (E-Sathi) service layer."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.billing.services.billing_service import CashOutService
from apps.customers.services.customer_service import CustomerService
from apps.finance.models import CashBookEntry, BankTransaction
from apps.finance.models.enums import (
    BankTransactionCategory,
    CashEntryCategory,
    CashEntryType,
)
from apps.finance.services.bank_service import BankService

User = get_user_model()


class CashOutServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cashier", password="Pass#123")
        self.account = BankService.create_account(
            account_name="Business A/C",
            bank_name="HDFC",
            account_number="501000000001",
            by=self.user,
        )
        self.customer = CustomerService.create_customer(
            data={"full_name": "Kavita", "phone": "9999000009"}, by=self.user
        )

    def _cash_out(self, transfer=5000, percent=1.5):
        return CashOutService.create_cash_out(
            data={
                "customer": self.customer,
                "bank_account": self.account,
                "transfer_amount": transfer,
                "commission_percent": percent,
            },
            by=self.user,
        )

    def test_cash_out_computes_commission_and_cash_given(self):
        cash_out = self._cash_out(transfer=5000, percent=1.5)
        self.assertEqual(cash_out.commission_amount, 75)
        self.assertEqual(cash_out.cash_given, 4925)
        self.assertEqual(cash_out.reference_number[:5], "COUT-")

    def test_cash_out_records_bank_deposit(self):
        self._cash_out()
        txn = BankTransaction.objects.get(category=BankTransactionCategory.PAYMENT_RECEIVED)
        self.assertEqual(txn.amount, 5000)
        self.assertEqual(txn.account, self.account)

    def test_cash_out_records_commission_income_and_cash_expense(self):
        self._cash_out()
        income = CashBookEntry.objects.get(
            entry_type=CashEntryType.INCOME, category=CashEntryCategory.COMMISSION
        )
        self.assertEqual(income.amount, 75)
        expense = CashBookEntry.objects.get(
            entry_type=CashEntryType.EXPENSE, category=CashEntryCategory.CASH_OUT
        )
        self.assertEqual(expense.amount, 4925)

    def test_zero_commission_means_full_cash(self):
        cash_out = self._cash_out(percent=0)
        self.assertEqual(cash_out.commission_amount, 0)
        self.assertEqual(cash_out.cash_given, 5000)
        self.assertFalse(
            CashBookEntry.objects.filter(category=CashEntryCategory.COMMISSION).exists()
        )

    def test_transfer_must_be_positive(self):
        with self.assertRaisesMessage(ValueError, "greater than zero"):
            self._cash_out(transfer=0)

    def test_commission_percentage_range(self):
        with self.assertRaisesMessage(ValueError, "between 0 and 100"):
            self._cash_out(percent=150)

    def test_bank_account_required(self):
        with self.assertRaisesMessage(ValueError, "bank account is required"):
            CashOutService.create_cash_out(
                data={"transfer_amount": 1000, "commission_percent": 1}, by=self.user
            )
