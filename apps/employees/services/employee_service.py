"""
EmployeeService — the only place employee lifecycle business rules live.

Views and forms never manipulate Employee records directly; they call
this service. Keeping the rules here guarantees that every path
(web form, admin action, future API, script) applies identical logic:

  * employee_code is generated centrally
  * a login account is always created together with the employee
  * the role group is always kept in sync with Employee.role
  * deactivation soft-deletes the employee AND locks the login
"""
from django.contrib.auth import get_user_model

from apps.employees.models import Employee, EmploymentStatus, Role
from apps.employees.services.role_service import assign_role_group
from apps.employees.services.wallet_service import WalletService

_EDITABLE_FIELDS = (
    "full_name",
    "role",
    "status",
    "gender",
    "date_of_birth",
    "date_of_joining",
    "personal_phone",
    "personal_email",
    "emergency_contact_name",
    "emergency_contact_phone",
    "address_line",
    "city",
    "state",
    "pincode",
    "id_proof_type",
    "id_proof_number",
    "notes",
)


class EmployeeService:
    @staticmethod
    def generate_employee_code() -> str:
        """Next sequential employee code in the form ANC-0001."""
        numbers = []
        for code in Employee.all_objects.values_list("employee_code", flat=True):
            try:
                numbers.append(int(code.rsplit("-", 1)[-1]))
            except (ValueError, IndexError):
                continue
        return f"ANC-{max(numbers, default=0) + 1:04d}"

    @staticmethod
    def create_employee(*, data: dict, by=None) -> Employee:
        """Create the login account + employee profile atomically."""
        User = get_user_model()
        username = str(data.get("username", "")).strip()
        password = data.get("password")

        if not username:
            raise ValueError("Username is required.")
        if not password:
            raise ValueError("Password is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValueError("A user with this username already exists.")

        role = data.get("role") or Role.STAFF
        if role not in Role.values:
            raise ValueError(f"Unknown role: {role}")

        user = User.objects.create_user(
            username=username,
            password=password,
            email=data.get("user_email") or None,
            phone=data.get("user_phone") or None,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        assign_role_group(user, role)

        full_name = str(data.get("full_name", "")).strip() or user.get_full_name()
        employee = Employee.objects.create(
            user=user,
            employee_code=EmployeeService.generate_employee_code(),
            full_name=full_name,
            role=role,
            status=data.get("status") or EmploymentStatus.ACTIVE,
            gender=data.get("gender", ""),
            date_of_birth=data.get("date_of_birth"),
            date_of_joining=data.get("date_of_joining"),
            personal_phone=data.get("personal_phone", ""),
            personal_email=data.get("personal_email", ""),
            emergency_contact_name=data.get("emergency_contact_name", ""),
            emergency_contact_phone=data.get("emergency_contact_phone", ""),
            address_line=data.get("address_line", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            pincode=data.get("pincode", ""),
            id_proof_type=data.get("id_proof_type", ""),
            id_proof_number=data.get("id_proof_number", ""),
            notes=data.get("notes", ""),
            created_by=by,
            updated_by=by,
        )
        # Every employee gets a wallet at birth (balance is zero until money moves).
        WalletService.get_or_create_wallet(employee)
        return employee

    @staticmethod
    def update_employee(employee: Employee, *, data: dict, by=None) -> Employee:
        """Apply only known editable fields and keep the role group in sync."""
        for field in _EDITABLE_FIELDS:
            if field in data:
                setattr(employee, field, data[field])
        employee.updated_by = by
        employee.save()

        if "role" in data:
            assign_role_group(employee.user, data["role"])
        return employee

    @staticmethod
    def deactivate_employee(employee: Employee, *, by=None) -> Employee:
        """Soft-delete the employee and revoke their login access."""
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active", "updated_at"])
        return employee.soft_delete(by=by)

    @staticmethod
    def restore_employee(employee: Employee, *, by=None) -> Employee:
        """Bring the employee and their login back."""
        employee.user.is_active = True
        employee.user.save(update_fields=["is_active", "updated_at"])
        return employee.restore(by=by)
