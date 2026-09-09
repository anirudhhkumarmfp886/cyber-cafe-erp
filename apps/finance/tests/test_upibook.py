"""Tests for UPI Book, strict cash book behavior, expense paid_from handling, and full float lifecycle."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Role, WalletType
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.wallet_service import WalletService
from apps.finance.forms.upibook import OwnerUPIFloatForm
from apps.finance.models import BankAccount, CashBookEntry, UPIBookEntry
from apps.finance.models.enums import BankTransactionCategory, BankTransactionType, CashEntryCategory
from apps.finance.selectors.cashbook_selector import CashBookSelector
from apps.finance.selectors.upibook_selector import UPIBookSelector
from apps.finance.services.bank_service import BankService
from apps.finance.services.cashbook_service import CashBookService
from apps.finance.services.upibook_service import UPIBookService

User = get_user_model()


class UPIBookAndCashBookTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        call_command("seed_roles")
        self.owner = EmployeeService.create_employee(
            data={"username": "upi-owner", "password": "Pass#123", "full_name": "UPI Owner", "role": Role.OWNER}
        )
        self.staff = EmployeeService.create_employee(
            data={"username": "upi-staff", "password": "Pass#123", "full_name": "UPI Staff", "role": Role.STAFF}
        )
        self.staff.can_record_expenses = True
        self.staff.save()
        self.bank = BankService.create_account(
            account_name="Main Shop SBI",
            bank_name="State Bank of India",
            account_number="112233445566",
            opening_balance=25000,
            is_default=True,
            by=self.owner.user,
        )

    def test_cashbook_only_counts_cash_entries(self):
        # Record a cash income
        CashBookService.record_income(
            amount=1000,
            category=CashEntryCategory.SALES,
            payment_mode="CASH",
            by=self.owner.user,
        )
        # Record a legacy non-cash entry in CashBookEntry directly
        CashBookEntry.objects.create(
            amount=5000,
            entry_type="INCOME",
            category="SALES",
            payment_mode="UPI",
            reference_number="CB-LEGACY-UPI",
            created_by=self.owner.user,
        )

        # CashBookSelector.balance() should only be 1000, NOT 6000!
        self.assertEqual(CashBookSelector.balance(), 1000)
        # list_entries() should only contain 1 cash entry
        entries = CashBookSelector.list_entries()
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().payment_mode, "CASH")

    def test_expense_paid_from_shop_drawer_does_not_debit_staff_wallet(self):
        # Give staff a wallet balance
        staff_wallet = WalletService.get_or_create_wallet(self.staff, WalletType.CASH)
        WalletService.credit(wallet=staff_wallet, amount=1000, by=self.owner.user)

        self.client.login(username="upi-staff", password="Pass#123")
        response = self.client.post(
            reverse("finance:cashbook_list"),
            {
                "entry_type": "EXPENSE",
                "category": "MISC",
                "paid_from": "SHOP_DRAWER",
                "payment_mode": "CASH",
                "amount": "150",
                "party_name": "Tea Stall",
                "description": "Chai for guests",
            },
        )
        self.assertEqual(response.status_code, 302)

        # CashBook should have recorded the expense
        self.assertEqual(CashBookEntry.objects.filter(category=CashEntryCategory.MISC).count(), 1)
        # Staff wallet should NOT have been debited! Balance is still 1000
        self.assertEqual(WalletService.balance_of(staff_wallet), 1000)

    def test_expense_paid_from_staff_float_debits_wallet_not_cashbook(self):
        staff_wallet = WalletService.get_or_create_wallet(self.staff, WalletType.CASH)
        WalletService.credit(wallet=staff_wallet, amount=1000, by=self.owner.user)

        self.client.login(username="upi-staff", password="Pass#123")
        response = self.client.post(
            reverse("finance:cashbook_list"),
            {
                "entry_type": "EXPENSE",
                "category": "MISC",
                "paid_from": "STAFF_FLOAT",
                "payment_mode": "CASH",
                "amount": "150",
                "party_name": "Stationery Shop",
                "description": "Paper clips from float",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Staff wallet should be debited from 1000 to 850
        self.assertEqual(WalletService.balance_of(staff_wallet), 850)
        # CashBook should NOT have a recorded expense for this (zero double deduction!)
        self.assertEqual(CashBookEntry.objects.filter(category=CashEntryCategory.MISC).count(), 0)

    def test_upibook_selector_and_view(self):
        # Record income via UPIBookService
        UPIBookService.record_income(
            amount=500,
            category=CashEntryCategory.SALES,
            bank_account=self.bank,
            party_name="QR Customer 1",
            description="Payment received on Soundbox",
            by=self.owner.user,
        )
        self.assertEqual(UPIBookSelector.today_inflow(), 500)
        self.assertEqual(UPIBookSelector.today_outflow(), 0)
        self.assertEqual(UPIBookSelector.balance(), 500)

        # Test view access
        self.client.login(username="upi-owner", password="Pass#123")
        response = self.client.get(reverse("finance:upibook_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shop UPI Book")
        self.assertContains(response, "QR Customer 1")

    def test_complete_bank_upibook_staff_float_cycle(self):
        """End-to-end verification of the exact lifecycle:
        1. Bank -> UPI Book float transfer (₹5,000)
        2. UPI Book -> Staff Online Wallet distribution (₹2,000)
        3. Customer UPI payment into UPI Book (₹1,100)
        4. Staff cash float replenishment from UPI pool (₹1,000)
        5. Staff returns remaining online float (₹2,000)
        6. Sweep float back to bank (₹5,000)
        7. Sweep profit to bank (₹100)
        """
        # Step 1: Owner funds ₹5,000 from Bank to UPI Book
        UPIBookService.fund_from_bank(
            bank_account=self.bank,
            amount=5000,
            description="Morning digital float load",
            by=self.owner.user,
        )
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.balance, 20000)
        self.assertEqual(UPIBookService.balance(), 5000)

        # Step 2: Distribute ₹2,000 online float to staff
        WalletService.top_up(
            employee=self.staff,
            wallet_type=WalletType.ONLINE,
            amount=2000,
            by=self.owner.user,
        )
        staff_online_wallet = WalletService.get_or_create_wallet(self.staff, WalletType.ONLINE)
        self.assertEqual(WalletService.balance_of(staff_online_wallet), 2000)
        self.assertEqual(UPIBookService.balance(), 3000)

        # Step 3: Customer pays ₹1,100 via UPI
        UPIBookService.record_income(
            amount=1100,
            category=CashEntryCategory.SALES,
            bank_account=self.bank,
            party_name="Customer Ramesh",
            description="Online service payment",
            by=self.owner.user,
        )
        self.assertEqual(UPIBookService.balance(), 4100)

        # Step 4: Reimburse ₹1,000 cash float to staff
        UPIBookService.reimburse_cash_float(
            amount=1000,
            staff=self.staff,
            description="Cash reimbursement for consumed float",
            by=self.owner.user,
        )
        staff_cash_wallet = WalletService.get_or_create_wallet(self.staff, WalletType.CASH)
        self.assertEqual(WalletService.balance_of(staff_cash_wallet), 1000)
        self.assertEqual(UPIBookService.balance(), 3100)

        # Step 5: Evening float return (Staff returns ₹2,000 online float)
        WalletService.return_float(
            employee=self.staff,
            wallet_type=WalletType.ONLINE,
            amount=2000,
            by=self.staff.user,
        )
        self.assertEqual(WalletService.balance_of(staff_online_wallet), 0)
        # UPI Book now has ₹3,100 + ₹2,000 = ₹5,100 (₹5,000 float + ₹100 profit)
        self.assertEqual(UPIBookService.balance(), 5100)

        # Step 6: Sweep ₹5,000 float back to Reserve Bank
        UPIBookService.sweep_to_bank(
            bank_account=self.bank,
            amount=5000,
            description="Daily float return to reserve bank",
            by=self.owner.user,
        )
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.balance, 25000)
        self.assertEqual(UPIBookService.balance(), 100)

        # Step 7: Sweep remaining ₹100 profit to Bank
        UPIBookService.sweep_to_bank(
            bank_account=self.bank,
            amount=100,
            description="Daily profit deposit to bank",
            by=self.owner.user,
        )
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.balance, 25100)
        self.assertEqual(UPIBookService.balance(), 0)

    def test_owner_upi_action_view_post(self):
        self.client.login(username="upi-owner", password="Pass#123")

        # 1. Load from Bank via View
        response = self.client.post(
            reverse("finance:upibook_action"),
            {
                "action": OwnerUPIFloatForm.Action.LOAD_FROM_BANK,
                "amount": "3000",
                "bank_account": str(self.bank.pk),
                "description": "Test load float via UI",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UPIBookService.balance(), 3000)

        # 2. Reimburse Cash via View
        response = self.client.post(
            reverse("finance:upibook_action"),
            {
                "action": OwnerUPIFloatForm.Action.REIMBURSE_CASH,
                "amount": "500",
                "staff": str(self.staff.pk),
                "description": "Test cash reimburse via UI",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UPIBookService.balance(), 2500)
        staff_cash = WalletService.get_or_create_wallet(self.staff, WalletType.CASH)
        self.assertEqual(WalletService.balance_of(staff_cash), 500)

        # 3. Sweep to Bank via View
        response = self.client.post(
            reverse("finance:upibook_action"),
            {
                "action": OwnerUPIFloatForm.Action.SWEEP_TO_BANK,
                "amount": "2500",
                "bank_account": str(self.bank.pk),
                "description": "Test sweep via UI",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UPIBookService.balance(), 0)

    def test_upibook_delete_and_bulk_delete(self):
        self.client.login(username="upi-owner", password="Pass#123")
        entry1 = UPIBookService.record_income(amount=1000, by=self.owner.user)
        entry2 = UPIBookService.record_income(amount=2000, by=self.owner.user)
        entry3 = UPIBookService.record_income(amount=3000, by=self.owner.user)

        self.assertEqual(UPIBookSelector.balance(), 6000)

        # Single Delete entry1
        response = self.client.post(reverse("finance:upibook_delete", kwargs={"pk": entry1.id}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UPIBookSelector.balance(), 5000)

        # Bulk Delete entry2 and entry3
        response = self.client.post(
            reverse("finance:upibook_bulk_delete"),
            {"selected_entries": [str(entry2.id), str(entry3.id)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UPIBookSelector.balance(), 0)

