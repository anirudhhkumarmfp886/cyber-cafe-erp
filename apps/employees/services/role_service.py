"""
Role <-> Group synchronisation.

Business roles (Employee.role) are mapped to Django auth Groups so that
the built-in permission framework enforces authorization. This is the
single source of truth for the mapping; the ``seed_roles`` management
command materialises the groups and their permissions.
"""
from django.contrib.auth.models import Group, Permission

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

BILLING_PERMISSION_CODENAMES = {
    "add_invoice",
    "view_invoice",
    "add_invoiceline",
    "view_invoiceline",
    "add_invoicepayment",
    "view_invoicepayment",
    "add_cashout",
    "view_cashout",
    "add_workentry",
    "change_workentry",
    "view_workentry",
    "add_cashbookincome",
    "add_customer",
    "view_customer",
}

TOPUP_PERMISSION_CODENAMES = {
    "withdraw_shop_cash",
    "add_wallettransaction",
    "view_wallettransaction",
    "change_wallet",
    "view_wallet",
}


def get_group_name_for_role(role) -> str:
    return ROLE_GROUP_MAP.get(role, ROLE_GROUP_MAP[Role.STAFF])


def assign_role_group(user, role) -> Group:
    """Place ``user`` in exactly one role group, removing any other role groups."""
    role_groups = Group.objects.filter(name__in=ALL_ROLE_GROUPS)
    user.groups.remove(*role_groups)
    group, _ = Group.objects.get_or_create(name=get_group_name_for_role(role))
    user.groups.add(group)
    return group


def sync_employee_permissions(employee) -> None:
    """Sync both group membership (from role) and direct user permissions (e.g. can_create_bills, can_manage_topup)."""
    user = employee.user
    assign_role_group(user, employee.role)

    billing_perms = list(Permission.objects.filter(codename__in=BILLING_PERMISSION_CODENAMES))
    if getattr(employee, "can_create_bills", False):
        user.user_permissions.add(*billing_perms)
    else:
        user.user_permissions.remove(*billing_perms)

    topup_perms = list(Permission.objects.filter(codename__in=TOPUP_PERMISSION_CODENAMES))
    if getattr(employee, "can_manage_topup", False):
        user.user_permissions.add(*topup_perms)
    else:
        user.user_permissions.remove(*topup_perms)

    # Clear in-memory permission cache on user instance if present
    for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        if hasattr(user, attr):
            delattr(user, attr)


def user_can_manage_topup(user) -> bool:
    """Check if the user is authorized to perform Owner Top-up or manage Owner Cash.

    Authorized if:
    - User is superuser / Owner
    - Employee has can_manage_topup == True
    - User has direct permission 'finance.withdraw_shop_cash'
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    employee = getattr(user, "employee", None)
    if employee:
        if employee.role == Role.OWNER or getattr(employee, "can_manage_topup", False):
            return True
    return user.has_perm("finance.withdraw_shop_cash")


def user_can_view_all_profiles(user) -> bool:
    """Check if the user is authorized to view all employees' full private profiles & ledgers.

    Authorized if:
    - User is superuser
    - Employee is Owner, Manager, or Accountant
    - User has change_employee or delete_employee permissions
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    employee = getattr(user, "employee", None)
    if employee and employee.role in (Role.OWNER, Role.MANAGER, Role.ACCOUNTANT):
        return True
    return user.has_perm("employees.change_employee") or user.has_perm("employees.delete_employee")


def user_can_manage_permissions(user) -> bool:
    """Check if the user is authorized to grant, revoke, or change staff permissions.

    Authorized if:
    - User is superuser
    - Employee has role == Role.OWNER
    - Employee has can_manage_permissions == True (explicitly granted by Owner)
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    employee = getattr(user, "employee", None)
    if employee:
        if employee.role == Role.OWNER:
            return True
        if getattr(employee, "can_manage_permissions", False):
            return True
    return False


def user_can_manage_customer_credit(user) -> bool:
    """Check if the user is authorized to set or change customer credit limits.

    Authorized if:
    - User is superuser / Owner
    - Employee has can_manage_customer_credit == True
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    employee = getattr(user, "employee", None)
    if employee:
        if employee.role == Role.OWNER:
            return True
        if getattr(employee, "can_manage_customer_credit", False):
            return True
    return False



