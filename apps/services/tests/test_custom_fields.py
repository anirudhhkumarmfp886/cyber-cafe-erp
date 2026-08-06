"""Tests for service categories + custom-field definitions."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import Role
from apps.employees.services.employee_service import EmployeeService
from apps.finance.services.bank_service import BankService
from apps.services.models import Category, ServiceCustomField
from apps.services.selectors.service_selector import ServiceSelector
from apps.services.services.service_service import ServiceService

User = get_user_model()


class CategoryServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="cat-owner")

    def test_new_category_created_and_assigned(self):
        service = ServiceService.create_service(
            data={"name": "Cash Withdrawal", "new_category": "Cash Withdrawal", "price": 50},
            by=self.owner,
        )
        self.assertEqual(service.category_name, "Cash Withdrawal")
        self.assertTrue(Category.objects.filter(name="Cash Withdrawal").exists())

    def test_legacy_category_code_mapped_to_seed_name(self):
        service = ServiceService.create_service(
            data={"name": "Gaming 1hr", "category": "GAMES", "price": 40}, by=self.owner
        )
        self.assertEqual(service.category_name, "Games")

    def test_default_category_is_other(self):
        service = ServiceService.create_service(
            data={"name": "Misc", "price": 10}, by=self.owner
        )
        self.assertEqual(service.category_name, "Other")


class CustomFieldServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="field-owner")
        self.manager = EmployeeService.create_employee(
            data={
                "username": "field-manager",
                "password": "StrongPass#123",
                "full_name": "Field Manager",
                "role": Role.MANAGER,
            },
            by=self.owner,
        ).user
        self.staff = EmployeeService.create_employee(
            data={
                "username": "field-staff",
                "password": "StrongPass#123",
                "full_name": "Field Staff",
                "role": Role.STAFF,
            },
            by=self.owner,
        ).user
        self.service = ServiceService.create_service(
            data={"name": "Cash Withdrawal", "new_category": "Cash", "price": 50},
            by=self.owner,
        )

    def test_create_custom_field_with_roles(self):
        field = ServiceService.create_custom_field(
            self.service,
            data={
                "label": "Withdrawal Amount",
                "field_type": "NUMBER",
                "required": True,
                "roles": ["MANAGER", "CASHIER"],
            },
            by=self.owner,
        )
        self.assertEqual(field.label, "Withdrawal Amount")
        self.assertEqual(field.role_list(), ["MANAGER", "CASHIER"])
        self.assertTrue(field.required)

    def test_delete_custom_field_is_soft(self):
        field = ServiceService.create_custom_field(
            self.service, data={"label": "Notes", "field_type": "TEXT"}, by=self.owner
        )
        ServiceService.delete_custom_field(field, by=self.owner)
        self.assertFalse(ServiceCustomField.objects.filter(pk=field.pk).exists())
        self.assertTrue(ServiceCustomField.all_objects.filter(pk=field.pk).exists())

    def test_visibility_respects_roles(self):
        ServiceService.create_custom_field(
            self.service,
            data={"label": "Secret", "field_type": "TEXT", "roles": ["MANAGER"]},
            by=self.owner,
        )
        ServiceService.create_custom_field(
            self.service,
            data={"label": "Public", "field_type": "TEXT", "roles": []},
            by=self.owner,
        )
        manager_visible = ServiceSelector.visible_custom_fields(self.service, self.manager)
        staff_visible = ServiceSelector.visible_custom_fields(self.service, self.staff)
        self.assertEqual({f.label for f in manager_visible}, {"Secret", "Public"})
        self.assertEqual({f.label for f in staff_visible}, {"Public"})

    def test_json_payload_includes_bank_accounts_for_bank_field(self):
        BankService.create_account(
            account_name="HDFC Main", bank_name="HDFC", account_number="999", by=self.owner
        )
        ServiceService.create_custom_field(
            self.service,
            data={"label": "Bank", "field_type": "BANK_ACCOUNT"},
            by=self.owner,
        )
        payload = ServiceSelector.custom_field_payload(self.service, self.manager)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["bank_accounts"][0]["name"], "HDFC Main (HDFC)")
