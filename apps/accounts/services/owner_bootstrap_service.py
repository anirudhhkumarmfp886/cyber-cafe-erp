"""
OwnerBootstrapService — first-run signup for the business owner.

Security model: the signup page only exists while NO superuser account has
been created. The moment the first owner registers, the page permanently
turns itself off. Staff are then added through the Employees module or the
admin, never through public registration. This keeps strangers out of a
money-handling ERP while giving the owner an easy way to bootstrap.

The created account is a Django superuser (full control) whose Employee
profile carries the Owner role, so role-based permissions work exactly like
for any other employee.
"""
from django.contrib.auth import get_user_model

from apps.employees.models import Employee, EmploymentStatus, Role
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import assign_role_group
from apps.employees.services.wallet_service import WalletService

User = get_user_model()


class OwnerBootstrapService:
    @staticmethod
    def is_bootstrap_required() -> bool:
        """True only while the very first owner account has not been created."""
        return not User.objects.filter(is_superuser=True).exists()

    @staticmethod
    def create_owner(*, username: str, password: str, email: str = "", phone: str = "") -> User:
        """Create the superuser + Owner employee profile atomically."""
        if not OwnerBootstrapService.is_bootstrap_required():
            raise ValueError("An owner account already exists. Signup is disabled.")

        user = User.objects.create_superuser(
            username=username,
            password=password,
            email=email or None,
            phone=phone or None,
        )
        assign_role_group(user, Role.OWNER)

        employee = Employee.objects.create(
            user=user,
            employee_code=EmployeeService.generate_employee_code(),
            full_name=user.get_full_name() or username,
            role=Role.OWNER,
            status=EmploymentStatus.ACTIVE,
            created_by=user,
            updated_by=user,
        )
        WalletService.get_or_create_wallet(employee)
        return user
