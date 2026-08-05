"""Tests for the wallet service layer (business rules)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import Employee, Role, WalletTransaction, WalletTransactionCategory
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService

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

    def test_new_employee_gets_a_wallet_at_birth(self):
        self.assertTrue(hasattr(self.staff, "wallet"))
        self.assertEqual(WalletService.balance_of(self.staff.wallet), 0)

    def test_credit_increases_balance_and_stamps_reference(self):
        txn = WalletService.credit(wallet=self.staff.wallet, amount=500, by=self.owner)
        self.assertEqual(txn.transaction_type, "CREDIT")
        self.assertTrue(txn.reference_number.startswith("WAL-"))
        self.assertEqual(WalletService.balance_of(self.staff.wallet), 500)
        self.assertEqual(txn.balance_after, 500)

    def test_debit_decreases_balance(self):
        WalletService.credit(wallet=self.staff.wallet, amount=1000, by=self.owner)
        WalletService.debit(wallet=self.staff.wallet, amount=400, by=self.owner)
        self.assertEqual(WalletService.balance_of(self.staff.wallet), 600)

    def test_debit_rejected_when_insufficient_balance(self):
        with self.assertRaisesMessage(ValueError, "Insufficient wallet balance"):
            WalletService.debit(wallet=self.staff.wallet, amount=100, by=self.owner)

    def test_zero_or_negative_amount_rejected(self):
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            WalletService.credit(wallet=self.staff.wallet, amount=0, by=self.owner)
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            WalletService.debit(wallet=self.staff.wallet, amount=-5, by=self.owner)

    def test_transfer_moves_money_atomically_and_cross_links(self):
        WalletService.credit(wallet=self.staff.wallet, amount=1000, by=self.owner)
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
        self.assertEqual(WalletService.balance_of(self.staff.wallet), 700)
        self.assertEqual(WalletService.balance_of(self.colleague.wallet), 300)

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
            wallet=self.staff.wallet,
            amount=15000,
            category=WalletTransactionCategory.SALARY,
            by=self.owner,
        )
        count = WalletTransaction.objects.filter(
            wallet=self.staff.wallet, category=WalletTransactionCategory.SALARY
        ).count()
        self.assertEqual(count, 1)
