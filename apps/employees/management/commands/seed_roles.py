"""
Create the role Groups and wire their permissions.

Run once after migrations (idempotent):

    python manage.py seed_roles

Permission matrix (Sprint 3):

    Role            Employee  Wallet   CashBook  Bank     Customer  Service  WorkLog
    ----------      --------- -------- --------  -------- --------- -------- --------
    Owner           full      full     full      full     full      full     full
    Manager         full      full     full      full     full      full     full
    Accountant      view      manage   manage    manage   view      view     view
    Cashier         view      view     view      view     view      view     view
    Counter Staff   view      view     view      view     view      view     view
    Staff           view      view     view      view     view      view     view

"manage" = add + change + delete + view. This command is re-run safely
whenever the matrix changes.
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from apps.customers.models import Customer
from apps.employees.models import Employee, Role, Wallet, WalletTransaction, WorkLogEntry
from apps.employees.services.role_service import ROLE_GROUP_MAP
from apps.finance.models import BankAccount, BankTransaction, CashBookEntry
from apps.services.models import Service, ServicePriceHistory

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
]

_READ_ONLY_PERMS = {"view"}


def _permissions_for(managed_models: set) -> set[str]:
    """codename set: view_* for every model, plus add/change/delete for managed ones."""
    perms = set()
    for model in _PERMISSION_MODELS:
        perms.add(f"view_{model._meta.model_name}")
        if model in managed_models:
            perms.add(f"add_{model._meta.model_name}")
            perms.add(f"change_{model._meta.model_name}")
            perms.add(f"delete_{model._meta.model_name}")
    return perms


class Command(BaseCommand):
    help = "Create role groups and assign permissions."

    def handle(self, *args, **options):
        # Gather every permission we care about for these models.
        content_types = ContentType.objects.get_for_models(*_PERMISSION_MODELS).values()
        all_perms = Permission.objects.filter(content_type__in=content_types)

        finance_models = {Wallet, WalletTransaction, CashBookEntry, BankAccount, BankTransaction}

        role_matrix = {
            Role.OWNER: _permissions_for(set(_PERMISSION_MODELS)),
            Role.MANAGER: _permissions_for(set(_PERMISSION_MODELS)),
            Role.ACCOUNTANT: _permissions_for(finance_models),
            Role.CASHIER: _permissions_for(set()),
            Role.COUNTER_STAFF: _permissions_for(set()),
            Role.STAFF: _permissions_for(set()),
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
