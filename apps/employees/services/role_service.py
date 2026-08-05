"""
Role <-> Group synchronisation.

Business roles (Employee.role) are mapped to Django auth Groups so that
the built-in permission framework enforces authorization. This is the
single source of truth for the mapping; the ``seed_roles`` management
command materialises the groups and their permissions.
"""
from django.contrib.auth.models import Group

from apps.employees.models import Role

ROLE_GROUP_MAP = {
    Role.OWNER: "Owner",
    Role.MANAGER: "Manager",
    Role.ACCOUNTANT: "Accountant",
    Role.CASHIER: "Cashier",
    Role.COUNTER_STAFF: "Counter Staff",
    Role.STAFF: "Staff",
}

ALL_ROLE_GROUPS = set(ROLE_GROUP_MAP.values())


def get_group_name_for_role(role) -> str:
    return ROLE_GROUP_MAP.get(role, ROLE_GROUP_MAP[Role.STAFF])


def assign_role_group(user, role) -> Group:
    """Place ``user`` in exactly one role group, removing any other role groups."""
    role_groups = Group.objects.filter(name__in=ALL_ROLE_GROUPS)
    user.groups.remove(*role_groups)
    group, _ = Group.objects.get_or_create(name=get_group_name_for_role(role))
    user.groups.add(group)
    return group
