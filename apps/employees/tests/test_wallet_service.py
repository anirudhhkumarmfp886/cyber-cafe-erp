"""Tests for the wallet service layer (business rules)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import Role, WalletTransaction, WalletTransactionCategory, WalletType
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService
from apps.finance.services.cashbook_service import CashBookService


User = get_user_model()


class WalletServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="wallet-owner")
        self.staff = self._make_employee("wallet-staff")
        self.colleague = self._make_employee("wallet-colleague")

    def _make_employee(self, username):
        return EmployeeService.create_employee(
            data={
                "username": username,
                "password": "StrongPass#123",
                "full_name": username.replace("-", " ").title(),
                "role": Role.STAFF,
            },
            by=self.owner,
        )

    def _cash_wallet(self, employee):
        return WalletService.get_or_create_wallet(employee, WalletType.CASH)

    def test_get_or_create_returns_stable_cash_wallet(self):
        first = self._cash_wallet(self.staff)
        second = self._cash_wallet(self.staff)
        self.assertEqual(first, second)
        self.assertEqual(WalletService.balance_of(first), 0)

    def test_credit_increases_balance_and_stamps_reference(self):
        txn = WalletService.credit(wallet=self._cash_wallet(self.staff), amount=500, by=self.owner)
        self.assertEqual(txn.transaction_type, "CREDIT")
        self.assertTrue(txn.reference_number.startswith("WAL-"))
        self.assertEqual(WalletService.balance_of(self._cash_wallet(self.staff)), 500)
        self.assertEqual(txn.balance_after, 500)

    def test_debit_decreases_balance(self):
        wallet = self._cash_wallet(self.staff)
        WalletService.credit(wallet=wallet, amount=1000, by=self.owner)
        WalletService.debit(wallet=wallet, amount=400, by=self.owner)
        self.assertEqual(WalletService.balance_of(wallet), 600)

    def test_debit_rejected_when_insufficient_balance(self):
        with self.assertRaisesMessage(ValueError, "Insufficient wallet balance"):
            WalletService.debit(wallet=self._cash_wallet(self.staff), amount=100, by=self.owner)

    def test_zero_or_negative_amount_rejected(self):
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            WalletService.credit(wallet=self._cash_wallet(self.staff), amount=0, by=self.owner)
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            WalletService.debit(wallet=self._cash_wallet(self.staff), amount=-5, by=self.owner)

    def test_transfer_moves_money_atomically_and_cross_links(self):
        WalletService.credit(wallet=self._cash_wallet(self.staff), amount=1000, by=self.owner)
        debit_txn, credit_txn = WalletService.transfer(
            from_employee=self.staff,
            to_employee=self.colleague,
            amount=300,
            by=self.owner,
        )
        self.assertEqual(debit_txn.category, WalletTransactionCategory.TRANSFER_OUT)
        self.assertEqual(credit_txn.category, WalletTransactionCategory.TRANSFER_IN)
        self.assertEqual(debit_txn.related_reference, credit_txn.reference_number)
        self.assertEqual(credit_txn.related_reference, debit_txn.reference_number)
        self.assertEqual(WalletService.balance_of(self._cash_wallet(self.staff)), 700)
        self.assertEqual(WalletService.balance_of(self._cash_wallet(self.colleague)), 300)

    def test_transfer_to_same_wallet_rejected(self):
        with self.assertRaisesMessage(ValueError, "Cannot transfer to the same wallet."):
            WalletService.transfer(
                from_employee=self.staff,
                to_employee=self.staff,
                amount=100,
                by=self.owner,
            )

    def test_transfer_declines_when_source_has_no_money(self):
        with self.assertRaisesMessage(ValueError, "Insufficient wallet balance."):
            WalletService.transfer(
                from_employee=self.staff,
                to_employee=self.colleague,
                amount=100,
                by=self.owner,
            )

    def test_salary_category_supported(self):
        WalletService.credit(
            wallet=self._cash_wallet(self.staff),
            amount=15000,
            category=WalletTransactionCategory.SALARY,
            by=self.owner,
        )
        count = WalletTransaction.objects.filter(
            wallet=self._cash_wallet(self.staff), category=WalletTransactionCategory.SALARY
        ).count()
        self.assertEqual(count, 1)

    def test_top_up_books_float_out_into_cash_book(self):
        CashBookService.owner_deposit(amount=5000, by=self.owner)
        WalletService.top_up(
            employee=self.staff,
            wallet_type=WalletType.CASH,
            amount=2000,
            by=self.owner,
        )
        self.assertEqual(WalletService.balance_of(self._cash_wallet(self.staff)), 2000)
        from apps.finance.models import CashBookEntry
        from apps.finance.models.enums import CashEntryCategory

        entry = CashBookEntry.objects.get(category=CashEntryCategory.FLOAT_OUT)
        self.assertEqual(entry.amount, 2000)
        self.assertEqual(entry.party_name, self.staff.full_name)
        self.assertIsNone(entry.staff)

    def test_return_float_cycle_resets_balance(self):
        CashBookService.owner_deposit(amount=5000, by=self.owner)
        # 1. Morning: owner gives ₹2,000 float
        WalletService.top_up(
            employee=self.staff,
            wallet_type=WalletType.CASH,
            amount=2000,
            by=self.owner,
        )
        self.assertEqual(WalletService.balance_of(self._cash_wallet(self.staff)), 2000)
        self.assertEqual(CashBookService.balance(), 3000)

        # 2. Evening: staff returns ₹2,000 float back to shop
        debit_txn, cash_entry = WalletService.return_float(
            employee=self.staff,
            wallet_type=WalletType.CASH,
            amount=2000,
            by=self.staff.user,
        )
        self.assertEqual(debit_txn.category, WalletTransactionCategory.FLOAT_OUT)
        from apps.finance.models.enums import CashEntryCategory
        self.assertEqual(cash_entry.category, CashEntryCategory.FLOAT_IN)
        # Staff wallet returns to 0
        self.assertEqual(WalletService.balance_of(self._cash_wallet(self.staff)), 0)
        # Shop cash drawer is back to 5000
        self.assertEqual(CashBookService.balance(), 5000)

    def test_top_up_cash_fails_on_insufficient_drawer_balance(self):
        CashBookService.owner_deposit(amount=500, by=self.owner)
        with self.assertRaises(ValueError) as ctx:
            WalletService.top_up(
                employee=self.staff,
                wallet_type=WalletType.CASH,
                amount=1000,
                by=self.owner,
            )
        self.assertIn("Insufficient shop cash drawer balance", str(ctx.exception))


