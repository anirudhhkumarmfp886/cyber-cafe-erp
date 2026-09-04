"""Tests for the Sprint 4.5 data migrations (backfill + work-entry import)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.billing.models import Invoice

User = get_user_model()


def _executor_at(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor


class WorkEntryImportMigrationTests(TransactionTestCase):
    """Run billing up to 0005, insert a SAVED WorkEntry, then migrate to 0007."""

    migrate_from = [
        ("billing", "0005_invoice_related_reference_and_more"),
        ("workentry", "0001_initial"),
        ("employees", "0007_employee_can_manage_topup"),
    ]
    migrate_to = [("billing", "0007_link_imported_work_entry_cash_entries")]

    def _old_models(self):
        apps = _executor_at(self.migrate_from).loader.project_state(self.migrate_from).apps
        WorkEntry = apps.get_model("workentry", "WorkEntry")
        Customer = apps.get_model("customers", "Customer")
        Service = apps.get_model("services", "Service")
        Employee = apps.get_model("employees", "Employee")
        User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        return WorkEntry, Customer, Service, Employee, User

    def _insert_work_entry(self, WorkEntry, Customer, Service, Employee, User, *, charged="100", total="100"):
        customer = Customer.objects.create(
            full_name="Migration Customer",
            phone="9999000077",
            credit_limit=0,
        )
        service = Service.objects.create(
            name="Printing Migration",
            price=5,
            description="",
            is_active=True,
        )
        user = User.objects.create(username="migration-staff")
        employee = Employee.objects.create(
            user=user,
            full_name="Migration Staff",
            role="STAFF",
            hourly_rate=0,
            can_create_bills=False,
            can_manage_topup=False,
        )
        entry = WorkEntry.objects.create(
            employee=employee,
            customer=customer,
            service=service,
            entry_date="2026-08-10",
            status="SAVED",
            payment_mode="CASH",
            charged_amount=charged,
            total=total,
            page_quantity="2",
            transfer_to_customer="0",
            transfer_on_behalf="0",
            cash_withdrawal="0",
            credit_used="0",
            credit_rest_mode="",
            reference_number="WE-000001",
            notes="import me",
            created_by=user,
            updated_by=user,
        )
        return entry

    def _migrate_to_latest(self):
        apps = _executor_at(self.migrate_to).loader.project_state(self.migrate_to).apps
        return apps

    def test_work_entry_imported_as_paid_invoice(self):
        WorkEntry, Customer, Service, Employee, User = self._old_models()
        self._insert_work_entry(WorkEntry, Customer, Service, Employee, User, charged="95", total="100")
        _executor_at(self.migrate_to)

        invoice = Invoice.objects.get(related_reference="WE-000001")
        self.assertEqual(invoice.invoice_number, "INV-000001")
        self.assertEqual(invoice.status, "PAID")
        self.assertEqual(invoice.total, Decimal("100.00"))
        self.assertEqual(invoice.billed_on.isoformat(), "2026-08-10")

        line = invoice.lines.get()
        self.assertEqual(line.qty, Decimal("2"))
        self.assertEqual(line.amount, Decimal("100.00"))
        self.assertEqual(line.income_amount, Decimal("95.00"))
        self.assertEqual(line.unit_price, Decimal("47.50"))

    def test_work_entry_legs_preserved_as_field_values(self):
        WorkEntry, Customer, Service, Employee, User = self._old_models()
        entry = self._insert_work_entry(
            WorkEntry, Customer, Service, Employee, User,
            charged="95", total="100",
        )
        entry.transfer_to_customer = "1000"
        entry.transfer_on_behalf = "200"
        entry.cash_withdrawal = "300"
        entry.credit_used = "0"
        entry.save()
        _executor_at(self.migrate_to)

        invoice = Invoice.objects.get(related_reference="WE-000001")
        line = invoice.lines.get()
        values = {v.field_label: v.value_text for v in line.field_values.all()}
        self.assertEqual(values["Charged Amount"], "95.00")
        self.assertEqual(values["Transfer to Customer"], "1000.00")
        self.assertEqual(values["Transfer on Behalf"], "200.00")
        self.assertEqual(values["Cash Withdrawal"], "300.00")

    def test_backfill_sets_income_amount_to_amount(self):
        # Create a legacy line with income_amount=0 through the pre-4.5 model,
        # then confirm the backfill patches it to income_amount = amount.
        apps = _executor_at(self.migrate_from).loader.project_state(self.migrate_from).apps
        Invoice = apps.get_model("billing", "Invoice")
        InvoiceLine = apps.get_model("billing", "InvoiceLine")
        Service = apps.get_model("services", "Service")
        service = Service.objects.create(
            name="Legacy Print",
            price=10,
            description="",
            is_active=True,
        )
        invoice = Invoice.objects.create(
            invoice_number="INV-999999",
            payment_mode="CASH",
            status="PAID",
            subtotal=0,
            discount=0,
            total=10,
            created_by_id=None,
            updated_by_id=None,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            service=service,
            description="legacy line",
            qty=1,
            unit_price=10,
            amount=10,
            income_amount=0,
            created_by_id=None,
            updated_by_id=None,
        )

        _executor_at(self.migrate_to)
        line = InvoiceLine.objects.get(description="legacy line")
        self.assertEqual(line.amount, Decimal("10.00"))
        self.assertEqual(line.income_amount, Decimal("10.00"))
