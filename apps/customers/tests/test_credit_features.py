"""Tests for customer credit limit audit log, staff wallet advance routing, and permissions."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.customers.models import CreditLogType, Customer, CustomerCreditLog
from apps.customers.selectors.customer_selector import CustomerSelector
from apps.customers.services.customer_service import CustomerService
from apps.employees.models import Employee, Role, WalletType
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import user_can_manage_customer_credit
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import CashBookEntry
from apps.finance.models.enums import CashEntryCategory

User = get_user_model()


class CustomerCreditFeatureTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        call_command("seed_roles")

        # Owner
        self.owner_user = User.objects.create_superuser(username="owner", password="OwnerPass#123")
        self.owner_emp = EmployeeService.create_employee(
            data={"username": "owner_emp", "password": "EmpPass#123", "full_name": "Shop Owner", "role": Role.OWNER},
            by=self.owner_user,
        )

        # Staff 1: Manish
        self.manish = EmployeeService.create_employee(
            data={"username": "manish", "password": "EmpPass#123", "full_name": "Manish Sharma", "role": Role.STAFF},
            by=self.owner_user,
        )

        # Staff 2: Aalekh
        self.aalekh = EmployeeService.create_employee(
            data={"username": "aalekh", "password": "EmpPass#123", "full_name": "Aalekh Kumar", "role": Role.MANAGER},
            by=self.owner_user,
        )

    def test_permission_toggle_and_check(self):
        # By default, Manish (STAFF) cannot manage customer credit
        self.assertFalse(user_can_manage_customer_credit(self.manish.user))
        # Owner can manage customer credit
        self.assertTrue(user_can_manage_customer_credit(self.owner_user))

        # Grant Aalekh permission
        EmployeeService.toggle_customer_credit_access(self.aalekh, by=self.owner_user)
        self.aalekh.refresh_from_db()
        self.assertTrue(self.aalekh.can_manage_customer_credit)
        self.assertTrue(user_can_manage_customer_credit(self.aalekh.user))

        # Revoke Aalekh permission
        EmployeeService.toggle_customer_credit_access(self.aalekh, by=self.owner_user)
        self.aalekh.refresh_from_db()
        self.assertFalse(self.aalekh.can_manage_customer_credit)
        self.assertFalse(user_can_manage_customer_credit(self.aalekh.user))

    def test_credit_limit_audit_trail_on_create_and_update(self):
        # 1. Manish creates customer Nitin with 1000 credit limit
        customer = CustomerService.create_customer(
            data={"full_name": "Nitin Verma", "phone": "9876543210", "credit_limit": 1000, "credit_limit_reason": "Regular client"},
            by=self.manish.user,
        )
        self.assertEqual(customer.credit_limit, Decimal("1000"))

        log1 = CustomerCreditLog.objects.filter(customer=customer, log_type=CreditLogType.LIMIT_CHANGE).first()
        self.assertIsNotNone(log1)
        self.assertEqual(log1.old_amount, Decimal("0"))
        self.assertEqual(log1.new_amount, Decimal("1000"))
        self.assertEqual(log1.change_amount, Decimal("1000"))
        self.assertEqual(log1.created_by, self.manish.user)

        # 2. Aalekh reduces credit limit to 200
        CustomerService.update_customer(
            customer,
            data={"credit_limit": 200, "credit_limit_reason": "Reduced due to delayed payments"},
            by=self.aalekh.user,
        )
        customer.refresh_from_db()
        self.assertEqual(customer.credit_limit, Decimal("200"))

        logs = CustomerSelector.get_limit_logs(customer)
        self.assertEqual(logs.count(), 2)
        latest_log = logs.first()
        self.assertEqual(latest_log.old_amount, Decimal("1000"))
        self.assertEqual(latest_log.new_amount, Decimal("200"))
        self.assertEqual(latest_log.change_amount, Decimal("-800"))
        self.assertEqual(latest_log.created_by, self.aalekh.user)
        self.assertIn("Reduced due to delayed payments", latest_log.notes)

    def test_customer_advance_deposit_routes_to_collecting_staff_wallet(self):
        customer = CustomerService.create_customer(
            data={"full_name": "Rohan Gupta", "phone": "9988776655"},
            by=self.owner_user,
        )

        # Manish collects ₹100 cash advance from Rohan
        CustomerService.adjust_credit(
            customer=customer,
            amount=100,
            payment_mode="CASH",
            payment_destination="STAFF",
            description="Advance for bulk scanning",
            by=self.manish.user,
        )

        customer.refresh_from_db()
        self.assertEqual(customer.credit_balance, Decimal("100"))

        # Check Manish's CASH wallet received ₹100
        manish_cash = WalletService.balance_of_employee(self.manish, WalletType.CASH)
        self.assertEqual(manish_cash, Decimal("100"))

        # Check CashBookEntry was recorded with staff=Manish
        entry = CashBookEntry.objects.filter(party_name="Rohan Gupta").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, Decimal("100"))
        self.assertEqual(entry.staff, self.manish)

        # Check CustomerCreditLog recorded
        credit_log = CustomerCreditLog.objects.filter(customer=customer, log_type=CreditLogType.PREPAID_DEPOSIT).first()
        self.assertIsNotNone(credit_log)
        self.assertEqual(credit_log.change_amount, Decimal("100"))
        self.assertEqual(credit_log.new_amount, Decimal("100"))
        self.assertEqual(credit_log.created_by, self.manish.user)
        self.assertEqual(credit_log.payment_mode, "CASH")

    def test_customer_advance_upi_deposit_routes_to_staff_online_wallet(self):
        customer = CustomerService.create_customer(
            data={"full_name": "Suresh", "phone": "9123456780"},
            by=self.owner_user,
        )

        # Aalekh collects ₹250 personal UPI advance during rush hour
        CustomerService.adjust_credit(
            customer=customer,
            amount=250,
            payment_mode="STAFF_UPI",
            payment_destination="STAFF",
            description="UPI advance for certificates",
            by=self.aalekh.user,
        )

        customer.refresh_from_db()
        self.assertEqual(customer.credit_balance, Decimal("250"))

        # Aalekh's ONLINE wallet should have ₹250
        aalekh_online = WalletService.balance_of_employee(self.aalekh, WalletType.ONLINE)
        self.assertEqual(aalekh_online, Decimal("250"))

    def test_customer_detail_financial_summary(self):
        customer = CustomerService.create_customer(
            data={"full_name": "Kavita", "credit_limit": 500},
            by=self.owner_user,
        )
        CustomerService.adjust_credit(customer=customer, amount=150, by=self.manish.user)
        customer.refresh_from_db()

        summary = CustomerSelector.get_financial_summary(customer)
        self.assertEqual(summary["credit_limit"], Decimal("500"))
        self.assertEqual(summary["credit_balance"], Decimal("150"))
        self.assertEqual(summary["outstanding_due"], Decimal("0"))
        self.assertEqual(summary["available_limit"], Decimal("500"))
