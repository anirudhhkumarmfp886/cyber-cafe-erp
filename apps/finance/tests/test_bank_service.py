"""Tests for the bank service layer (business rules)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import BankTransaction
from apps.finance.models.enums import BankTransactionCategory, BankTransactionType
from apps.finance.services.bank_service import BankService

User = get_user_model()


class BankServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bank-user")
        self.account_a = BankService.create_account(
            account_name="Business Current",
            bank_name="HDFC",
            account_number="1234567890",
            opening_balance=1000,
            by=self.user,
        )
        self.account_b = BankService.create_account(
            account_name="Savings",
            bank_name="SBI",
            account_number="0987654321",
            by=self.user,
        )

    def test_create_account_requires_identity(self):
        with self.assertRaisesMessage(ValueError, "required"):
            BankService.create_account(
                account_name="", bank_name="HDFC", account_number="111", by=self.user
            )

    def test_balance_starts_from_opening_balance(self):
        self.assertEqual(BankService.balance_of(self.account_a), 1000)
        self.assertEqual(BankService.balance_of(self.account_b), 0)

    def test_deposit_credits(self):
        txn = BankService.deposit(account=self.account_a, amount=5000, by=self.user)
        self.assertEqual(txn.transaction_type, BankTransactionType.CREDIT)
        self.assertTrue(txn.reference_number.startswith("BANK-"))
        self.assertEqual(BankService.balance_of(self.account_a), 6000)

    def test_withdraw_debits(self):
        BankService.deposit(account=self.account_a, amount=500, by=self.user)
        BankService.withdraw(account=self.account_a, amount=200, by=self.user)
        self.assertEqual(BankService.balance_of(self.account_a), 1300)

    def test_withdraw_rejected_when_insufficient(self):
        with self.assertRaisesMessage(ValueError, "Insufficient bank balance."):
            BankService.withdraw(account=self.account_a, amount=5000, by=self.user)

    def test_transfer_moves_money_and_cross_links(self):
        BankService.deposit(account=self.account_a, amount=4000, by=self.user)
        debit_txn, credit_txn = BankService.transfer(
            from_account=self.account_a,
            to_account=self.account_b,
            amount=1500,
            by=self.user,
        )
        self.assertEqual(debit_txn.category, BankTransactionCategory.TRANSFER_OUT)
        self.assertEqual(credit_txn.category, BankTransactionCategory.TRANSFER_IN)
        self.assertEqual(debit_txn.related_reference, credit_txn.reference_number)
        self.assertEqual(credit_txn.related_reference, debit_txn.reference_number)
        self.assertEqual(BankService.balance_of(self.account_a), 3500)
        self.assertEqual(BankService.balance_of(self.account_b), 1500)

    def test_transfer_to_same_account_rejected(self):
        with self.assertRaisesMessage(ValueError, "Cannot transfer to the same account."):
            BankService.transfer(
                from_account=self.account_a,
                to_account=self.account_a,
                amount=100,
                by=self.user,
            )

    def test_zero_or_negative_amount_rejected(self):
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            BankService.deposit(account=self.account_a, amount=0, by=self.user)
        with self.assertRaisesMessage(ValueError, "Amount must be greater than zero."):
            BankService.withdraw(account=self.account_a, amount=-10, by=self.user)

    def test_transactions_are_appended_never_edited(self):
        BankService.deposit(account=self.account_a, amount=100, by=self.user)
        BankService.deposit(account=self.account_a, amount=200, by=self.user)
        count = BankTransaction.objects.filter(account=self.account_a).count()
        self.assertEqual(count, 2)
        self.assertEqual(BankService.balance_of(self.account_a), 1300)
