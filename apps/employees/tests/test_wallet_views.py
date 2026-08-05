"""Tests for wallet, cash book and bank web views + permission enforcement."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.services.owner_bootstrap_service import OwnerBootstrapService
from apps.employees.models import Role
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import assign_role_group
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import BankAccount
from apps.finance.models.enums import CashEntryCategory
from apps.finance.services.bank_service import BankService
from apps.finance.services.cashbook_service import CashBookService

User = get_user_model()


class StaffModuleViewTests(TestCase):
    """Exercises the Sprint 2 screens end-to-end as a permissioned user."""

    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        OwnerBootstrapService.create_owner(username="boss", password="OwnerPass#123")
        boss = User.objects.get(username="boss")
        self.manager = EmployeeService.create_employee(
            data={
                "username": "manager",
                "password": "StrongPass#123",
                "full_name": "The Manager",
                "role": Role.MANAGER,
            },
            by=boss,
        )
        self.staff = EmployeeService.create_employee(
            data={
                "username": "staff",
                "password": "StrongPass#123",
                "full_name": "A Staffer",
                "role": Role.STAFF,
            },
            by=boss,
        )
        self.client.login(username="manager", password="StrongPass#123")

    def test_wallet_list_shows_balance(self):
        WalletService.credit(wallet=self.staff.wallet, amount=250, by=self.manager.user)
        response = self.client.get(reverse("employees:wallet_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A Staffer")
        self.assertContains(response, "250.00")

    def test_wallet_detail_credit_action(self):
        response = self.client.post(
            reverse("employees:wallet_detail", kwargs={"pk": self.staff.wallet.pk}),
            {"action": "credit", "amount": "750", "category": "CASH_TOPUP"},
        )
        self.assertRedirects(
            response,
            reverse("employees:wallet_detail", kwargs={"pk": self.staff.wallet.pk}),
        )
        self.assertEqual(WalletService.balance_of(self.staff.wallet), 750)

    def test_wallet_detail_insufficient_debit_shows_error(self):
        response = self.client.post(
            reverse("employees:wallet_detail", kwargs={"pk": self.staff.wallet.pk}),
            {"action": "debit", "amount": "99999", "category": "CASH_WITHDRAWAL"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insufficient wallet balance")

    def test_cashbook_list_records_income(self):
        response = self.client.post(
            reverse("finance:cashbook_list"),
            {
                "entry_type": "INCOME",
                "amount": "1200",
                "category": CashEntryCategory.SALES,
                "payment_mode": "UPI",
            },
        )
        self.assertRedirects(response, reverse("finance:cashbook_list"))
        self.assertEqual(CashBookService.balance(), 1200)

    def test_cashbook_list_category_mismatch_rejected(self):
        response = self.client.post(
            reverse("finance:cashbook_list"),
            {
                "entry_type": "EXPENSE",
                "amount": "1200",
                "category": CashEntryCategory.SALES,
                "payment_mode": "CASH",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not valid for")

    def test_bank_list_creates_account(self):
        response = self.client.post(
            reverse("finance:bank_list"),
            {
                "account_name": "Business HDFC",
                "bank_name": "HDFC Bank",
                "account_number": "111122223333",
                "account_type": "CURRENT",
            },
        )
        self.assertRedirects(response, reverse("finance:bank_list"))
        self.assertTrue(BankAccount.objects.filter(account_number="111122223333").exists())

    def test_bank_detail_deposit_action(self):
        account = BankService.create_account(
            account_name="Business HDFC",
            bank_name="HDFC Bank",
            account_number="999988887777",
            by=self.manager.user,
        )
        response = self.client.post(
            reverse("finance:bank_detail", kwargs={"pk": account.pk}),
            {"action": "deposit", "amount": "5000"},
        )
        self.assertRedirects(response, reverse("finance:bank_detail", kwargs={"pk": account.pk}))
        self.assertEqual(BankService.balance_of(account), 5000)

    def test_bank_detail_statement_renders_credit_and_debit_columns(self):
        account = BankService.create_account(
            account_name="Business HDFC",
            bank_name="HDFC Bank",
            account_number="555566667777",
            by=self.manager.user,
        )
        BankService.deposit(account=account, amount=5000, party_name="Walk-in", by=self.manager.user)
        BankService.withdraw(account=account, amount=1500, party_name="Electricity", by=self.manager.user)
        response = self.client.get(reverse("finance:bank_detail", kwargs={"pk": account.pk}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertRegex(content, r'class="text-end text-success fw-semibold">\s*₹5000\.00')
        self.assertRegex(content, r'class="text-end text-danger fw-semibold">\s*₹1500\.00')


class PermissionEnforcementTests(TestCase):
    """Low-privilege roles must be denied on write actions."""

    def setUp(self):
        from django.core.management import call_command

        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.lowly = User.objects.create_user(username="counter", password="StrongPass#123")
        assign_role_group(self.lowly, Role.STAFF)
        self.client.login(username="counter", password="StrongPass#123")

    def test_staff_cannot_open_cashbook_add_form_but_can_view(self):
        response = self.client.get(reverse("finance:cashbook_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Record Entry")

    def test_staff_cannot_post_cashbook_entry(self):
        response = self.client.post(
            reverse("finance:cashbook_list"),
            {"entry_type": "INCOME", "amount": "100", "category": "SALES"},
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_post_wallet_action(self):
        staff_emp = EmployeeService.create_employee(
            data={
                "username": "staffemp",
                "password": "StrongPass#123",
                "full_name": "Staff Employee",
                "role": Role.STAFF,
            },
            by=self.boss,
        )
        response = self.client.post(
            reverse("employees:wallet_detail", kwargs={"pk": staff_emp.wallet.pk}),
            {"action": "credit", "amount": "100", "category": "CASH_TOPUP"},
        )
        self.assertEqual(response.status_code, 403)
