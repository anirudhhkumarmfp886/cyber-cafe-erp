"""Tests for billing with service custom fields (incl. auto bank deposit)."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.billing.services.billing_service import BillingService
from apps.employees.models import Role
from apps.employees.services.employee_service import EmployeeService
from apps.finance.models import BankTransaction
from apps.finance.models.enums import BankTransactionCategory
from apps.finance.services.bank_service import BankService
from apps.services.services.service_service import ServiceService

User = get_user_model()


class CustomFieldBillingServiceTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = User.objects.create_user(username="cfb-owner")
        self.manager = EmployeeService.create_employee(
            data={
                "username": "cfb-manager",
                "password": "StrongPass#123",
                "full_name": "CFB Manager",
                "role": Role.MANAGER,
            },
            by=self.owner,
        ).user
        self.staff = EmployeeService.create_employee(
            data={
                "username": "cfb-staff",
                "password": "StrongPass#123",
                "full_name": "CFB Staff",
                "role": Role.STAFF,
            },
            by=self.owner,
        ).user
        self.service = ServiceService.create_service(
            data={"name": "Cash Withdrawal", "new_category": "Cash", "price": 50},
            by=self.owner,
        )
        self.account = BankService.create_account(
            account_name="HDFC Main", bank_name="HDFC", account_number="555", by=self.owner
        )

    def _add_field(self, label, field_type, required=False, roles=None):
        return ServiceService.create_custom_field(
            self.service,
            data={
                "label": label,
                "field_type": field_type,
                "required": required,
                "roles": roles or [],
            },
            by=self.owner,
        )

    def _bill(self, custom, by):
        return BillingService.create_invoice(
            data={"payment_mode": "CASH", "discount": 0},
            lines=[{"service": self.service, "qty": 1, "custom": custom}],
            by=by,
        )

    def test_text_and_number_values_stored_on_line(self):
        amount = self._add_field("Withdrawal Amount", "NUMBER", required=True)
        ref = self._add_field("Reference", "TEXT")
        invoice = self._bill(
            {str(amount.pk): "5000", str(ref.pk): "SBI NEFT ref 123"}, by=self.manager
        )
        line = invoice.lines.get()
        values = {v.field_label: v.value_text for v in line.field_values.all()}
        self.assertEqual(values["Withdrawal Amount"], "5000.00")
        self.assertEqual(values["Reference"], "SBI NEFT ref 123")

    def test_required_field_missing_rejected(self):
        self._add_field("Withdrawal Amount", "NUMBER", required=True)
        with self.assertRaisesMessage(ValueError, "is required"):
            self._bill({}, by=self.manager)

    def test_bank_transfer_books_deposit_into_chosen_account(self):
        transfer = self._add_field("Transfer Amount", "BANK_TRANSFER", required=True)
        bank = self._add_field("Bank Account", "BANK_ACCOUNT", required=True)
        invoice = self._bill(
            {str(transfer.pk): "5000", str(bank.pk): str(self.account.pk)},
            by=self.manager,
        )
        line = invoice.lines.get()
        bank_value = line.field_values.get(field_type="BANK_ACCOUNT")
        self.assertEqual(bank_value.bank_account, self.account)
        deposit = BankTransaction.objects.filter(
            account=self.account, category=BankTransactionCategory.PAYMENT_RECEIVED
        )
        self.assertEqual(deposit.count(), 1)
        self.assertEqual(deposit.first().amount, 5000)

    def test_bank_transfer_without_account_rejected(self):
        transfer = self._add_field("Transfer Amount", "BANK_TRANSFER", required=True)
        self._add_field("Bank Account", "BANK_ACCOUNT")
        with self.assertRaisesMessage(ValueError, "bank account"):
            self._bill({str(transfer.pk): "5000"}, by=self.manager)

    def test_role_gated_field_rejected_for_staff(self):
        field = self._add_field("Commission", "PERCENT", roles=["MANAGER"])
        with self.assertRaisesMessage(ValueError, "do not have permission"):
            self._bill({str(field.pk): "2"}, by=self.staff)

    def test_role_gated_field_allowed_for_manager(self):
        field = self._add_field("Commission", "PERCENT", roles=["MANAGER"])
        invoice = self._bill({str(field.pk): "2"}, by=self.manager)
        line = invoice.lines.get()
        self.assertEqual(line.field_values.get().display_value, "2%")

    def test_percent_validation(self):
        field = self._add_field("Commission", "PERCENT", required=True)
        with self.assertRaisesMessage(ValueError, "between 0 and 100"):
            self._bill({str(field.pk): "150"}, by=self.manager)


class CustomFieldBillingViewTests(TestCase):
    def setUp(self):
        call_command("seed_roles")
        self.owner = User.objects.create_superuser(username="cfb-boss", password="OwnerPass#123")
        self.staff = EmployeeService.create_employee(
            data={
                "username": "cfb-staff2",
                "password": "StrongPass#123",
                "full_name": "Staff Two",
                "role": Role.STAFF,
            },
            by=self.owner,
        ).user
        self.service = ServiceService.create_service(
            data={"name": "Printing B/W", "new_category": "Printing", "price": 5},
            by=self.owner,
        )

    def test_owner_can_create_custom_field(self):
        self.client.login(username="cfb-boss", password="OwnerPass#123")
        response = self.client.post(
            reverse("services:field_create", kwargs={"pk": self.service.pk}),
            {"label": "Pages", "field_type": "NUMBER", "required": "on", "roles": ["MANAGER"]},
        )
        self.assertRedirects(
            response, reverse("services:detail", kwargs={"pk": self.service.pk})
        )
        self.assertTrue(
            self.service.custom_fields.filter(label="Pages", field_type="NUMBER").exists()
        )

    def test_staff_cannot_create_custom_field(self):
        self.client.login(username="cfb-staff2", password="StrongPass#123")
        response = self.client.post(
            reverse("services:field_create", kwargs={"pk": self.service.pk}),
            {"label": "Pages", "field_type": "NUMBER"},
        )
        self.assertEqual(response.status_code, 403)

    def test_json_endpoint_returns_fields_for_billing(self):
        ServiceService.create_custom_field(
            self.service,
            data={"label": "Pages", "field_type": "NUMBER", "required": True},
            by=self.owner,
        )
        self.client.login(username="cfb-boss", password="OwnerPass#123")
        response = self.client.get(
            reverse("services:custom_fields_json"), {"service": str(self.service.pk)}
        )
        self.assertEqual(response.status_code, 200)
        fields = response.json()["fields"]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["label"], "Pages")
        self.assertTrue(fields[0]["required"])
