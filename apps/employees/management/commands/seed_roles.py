"""
Create the role Groups and wire their permissions.

Run once after migrations (idempotent):

    python manage.py seed_roles

Permission matrix (Sprint 2):

    Role            Employee   Wallet    Cash Book   Bank
    ----------      ---------  --------  ----------  ------
    Owner           full       full      full        full
    Manager         full       full      full        full
    Accountant      view       manage    manage      manage
    Cashier         view       view      view        view
    Counter Staff   view       view      view        view
    Staff           view       view      view        view

"manage" = add + change + delete + view. This command is re-run safely
whenever the matrix changes.
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from apps.employees.models import Employee, Role, Wallet, WalletTransaction
from apps.employees.services.role_service import ROLE_GROUP_MAP
from apps.finance.models import BankAccount, BankTransaction, CashBookEntry

_PERMISSION_MODELS = [Employee, Wallet, WalletTransaction, CashBookEntry, BankAccount, BankTransaction]

_READ_ONLY_PERMS = {"view"}


def _group_permissions(role, managed: bool) -> set[str]:
    """codename set: add_*, change_*, delete_*, view_* for each model."""
    perms = set()
    for model in _PERMISSION_MODELS:
        perms.add(f"view_{model._meta.model_name}")
        if managed:
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

        role_matrix = {
            Role.OWNER: _group_permissions(Role.OWNER, managed=True),
            Role.MANAGER: _group_permissions(Role.MANAGER, managed=True),
            Role.ACCOUNTANT: _group_permissions(Role.ACCOUNTANT, managed=True),
            Role.CASHIER: _group_permissions(Role.CASHIER, managed=False),
            Role.COUNTER_STAFF: _group_permissions(Role.COUNTER_STAFF, managed=False),
            Role.STAFF: _group_permissions(Role.STAFF, managed=False),
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
