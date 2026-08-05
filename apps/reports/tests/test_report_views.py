"""Tests for the reports app (HTML pages + CSV export)."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.billing.services.billing_service import BillingService
from apps.customers.services.customer_service import CustomerService
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.worklog_service import WorkLogService
from apps.finance.services.bank_service import BankService
from apps.finance.services.cashbook_service import CashBookService
from apps.services.services.service_service import ServiceService

User = get_user_model()


class ReportViewTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.boss = User.objects.create_superuser(username="boss", password="OwnerPass#123")
        self.client.login(username="boss", password="OwnerPass#123")

        self.gaming = ServiceService.create_service(
            data={"name": "Gaming 1hr", "price": 40}, by=self.boss
        )
        self.printing = ServiceService.create_service(
            data={"name": "Printing", "price": 2}, by=self.boss
        )
        self.customer = CustomerService.create_customer(
            data={"full_name": "Rahul", "phone": "9999000001", "credit_limit": 500},
            by=self.boss,
        )
        self.account = BankService.create_account(
            account_name="HDFC", bank_name="HDFC", account_number="5010000001", by=self.boss
        )

    def test_report_index_renders(self):
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profit &amp; Loss")

    def test_profit_loss_renders_totals(self):
        CashBookService.record_income(amount=100, category="SALES", by=self.boss)
        CashBookService.record_expense(amount=30, category="RENT", by=self.boss)
        response = self.client.get(reverse("reports:profit_loss"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Net Profit")
        self.assertContains(response, "100.00")
        self.assertContains(response, "30.00")

    def test_profit_loss_csv_export(self):
        CashBookService.record_income(amount=100, category="SALES", by=self.boss)
        response = self.client.get(f"{reverse('reports:profit_loss')}?export=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertContains(response, "NET PROFIT")

    def test_bank_statement_renders(self):
        BankService.deposit(account=self.account, amount=1000, by=self.boss)
        response = self.client.get(reverse("reports:bank_statement"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HDFC")
        self.assertContains(response, "Closing Balance")

    def test_customer_ledger_renders_totals(self):
        invoice = BillingService.create_invoice(
            data={"customer": self.customer, "payment_mode": "CREDIT"},
            lines=[(self.gaming, 2)],
            by=self.boss,
        )
        BillingService.settle_invoice(invoice=invoice, amount=40, payment_mode="CASH", by=self.boss)
        response = self.client.get(reverse("reports:customer_ledger"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rahul")
        self.assertContains(response, "TOTALS")

    def test_customer_ledger_csv(self):
        response = self.client.get(f"{reverse('reports:customer_ledger')}?export=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_wallet_statement_renders(self):
        EmployeeService.create_employee(
            data={
                "username": "manish",
                "password": "Pass#123",
                "full_name": "Manish Kumar",
                "role": "STAFF",
            },
            by=self.boss,
        )
        response = self.client.get(reverse("reports:wallet_statement"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manish Kumar")

    def test_salary_summary_renders(self):
        employee = EmployeeService.create_employee(
            data={
                "username": "salary-guy",
                "password": "Pass#123",
                "full_name": "Salary Guy",
                "role": "STAFF",
                "hourly_rate": 100,
            },
            by=self.boss,
        )
        entry = WorkLogService.create_entry(employee=employee, work_date="2026-08-05", hours_worked=2, by=self.boss)
        WorkLogService.approve_entry(entry, by=self.boss)
        response = self.client.get(reverse("reports:salary_summary"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salary Guy")
        self.assertContains(response, "200.00")

    def test_analytics_renders(self):
        BillingService.create_invoice(
            data={"customer": self.customer, "payment_mode": "CASH"},
            lines=[(self.gaming, 2), (self.printing, 5)],
            by=self.boss,
        )
        response = self.client.get(reverse("reports:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Peak Hours")
        self.assertContains(response, "Gaming 1hr")

    def test_reports_require_login(self):
        self.client.logout()
        for name in ("profit_loss", "bank_statement", "customer_ledger", "wallet_statement", "salary_summary", "analytics"):
            response = self.client.get(reverse(f"reports:{name}"))
            self.assertEqual(response.status_code, 302)
