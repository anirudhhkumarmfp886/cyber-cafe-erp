"""
Create the role Groups and wire their permissions.

Run once after migrations (idempotent):

    python manage.py seed_roles

Permission matrix (Sprint 4 + Phase 1):

    Role            Employee  Wallet   CashBook  Bank     Customer  Service  WorkLog  Billing
    ----------      --------- -------- --------  -------- --------- -------- -------- --------
    Owner           full      full     full      full     full      full     full     full
    Manager         full      full     full      full     full      full     full     full
    Accountant      view      manage   manage    manage   view      view     view     manage
    Cashier         view      view     view      view     view      view     view     create
    Counter Staff   view      view     view      view     view      view     view     create
    Staff           view      view     view      view     view      view     view     view

    WorkEntry permissions (new): Owner/Manager full; Accountant manage;
    Cashier and Counter Staff add+change+view (they create and finalize
    their own bills, but cannot void); Staff view only.

Cash book custom permissions (Phase 1): Owner/Manager/Accountant can record
manual income AND expense plus owner cash withdraw/deposit. Cashier and
Counter Staff can record manual INCOME only (they already generate expense
side via cash-outs). Staff have no manual cash book entry rights.

"manage" = add + change + delete + view. "create" = add + view (counter
staff can bill and cash-out but cannot edit or void). This command is
re-run safely whenever the matrix changes.
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from apps.billing.models import CashOut, Invoice, InvoiceLine, InvoicePayment
from apps.customers.models import Customer
from apps.employees.models import Employee, Role, Wallet, WalletTransaction, WorkLogEntry
from apps.employees.services.role_service import ROLE_GROUP_MAP
from apps.finance.models import BankAccount, BankTransaction, CashBookEntry
from apps.services.models import Category, Service, ServiceCustomField, ServicePriceHistory
from apps.workentry.models import WorkEntry
from apps.inventory.models import StockItem, StockMovement

_PERMISSION_MODELS = [
    Employee,
    Wallet,
    WalletTransaction,
    WorkLogEntry,
    CashBookEntry,
    BankAccount,
    BankTransaction,
    Customer,
    Service,
    ServicePriceHistory,
    Category,
    ServiceCustomField,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    CashOut,
    WorkEntry,
    StockItem,
    StockMovement,
]


def _view_permissions(models) -> set[str]:
    return {f"view_{model._meta.model_name}" for model in models}


def _manage_permissions(models) -> set[str]:
    perms = _view_permissions(models)
    for model in models:
        name = model._meta.model_name
        perms.update({f"add_{name}", f"change_{name}", f"delete_{name}"})
    return perms


def _create_permissions(models) -> set[str]:
    """view + add — enough to bill and cash-out, but not to edit/void."""
    perms = _view_permissions(models)
    perms.update({f"add_{model._meta.model_name}" for model in models})
    return perms


class Command(BaseCommand):
    help = "Create role groups and assign permissions."

    def handle(self, *args, **options):
        # Gather every permission we care about for these models.
        content_types = ContentType.objects.get_for_models(*_PERMISSION_MODELS).values()
        all_perms = Permission.objects.filter(content_type__in=content_types)

        all_models = set(_PERMISSION_MODELS)
        finance_models = {Wallet, WalletTransaction, CashBookEntry, BankAccount, BankTransaction}
        inventory_models = {StockItem, StockMovement}
        billing_models = {Invoice, InvoiceLine, InvoicePayment, CashOut}

        # Custom-field definitions are owner-managed: everyone can view them
        # (view is included in every role below) but only the Owner can add,
        # change or delete them.
        custom_field_manage = {
            f"{prefix}_servicecustomfield"
            for prefix in ("add", "change", "delete")
        }

        # Cash book custom permissions (Phase 1): income-only / expense-only
        # manual entry control plus the owner cash (withdraw/deposit) action.
        cash_income = {"add_cashbookincome"}
        cash_expense = {"add_cashbookexpense"}
        cash_withdraw = {"withdraw_shop_cash"}
        cash_full = cash_income | cash_expense | cash_withdraw

        # Work entry: counter staff create a draft and finalize the bill, so
        # they need add + change (no delete). Accountants manage/void entries.
        workentry_models = {WorkEntry}
        work_entry_work = {
            f"{prefix}_workentry"
            for prefix in ("add", "change", "view")
        }

        role_matrix = {
            Role.OWNER: _manage_permissions(all_models) | cash_full,
            Role.MANAGER: (_manage_permissions(all_models) - custom_field_manage) | cash_full,
            Role.ACCOUNTANT: _view_permissions(all_models)
            | _manage_permissions(finance_models | billing_models | workentry_models | inventory_models)
            | cash_full,
            Role.CASHIER: _view_permissions(all_models)
            | _create_permissions(billing_models)
            | work_entry_work
            | cash_income,
            Role.COUNTER_STAFF: _view_permissions(all_models)
            | _create_permissions(billing_models)
            | work_entry_work
            | cash_income,
            Role.STAFF: _view_permissions(all_models),
        }

        new_groups = 0
        for role, group_name in ROLE_GROUP_MAP.items():
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                new_groups += 1
            wanted = role_matrix[role]
            group.permissions.set(all_perms.filter(codename__in=wanted))
            self.stdout.write(
                self.style.SUCCESS(f"Group '{group_name}' -> {group.permissions.count()} permission(s)")
            )
        self.stdout.write(self.style.SUCCESS(f"Seeding complete. New groups created: {new_groups}"))
