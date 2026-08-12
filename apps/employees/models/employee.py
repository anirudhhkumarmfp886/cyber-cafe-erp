"""
Employee — the business profile behind a login account.

One login (accounts.User) maps to exactly one Employee. The employee
carries HR data (identity, contact, role, employment status) while the
login carries credentials. Wallet, attendance and salary fields arrive
in later sprints and will live in dedicated models next to this one.
"""
from django.conf import settings
from django.db import models

from apps.common.models import BaseModel, money_field


class Role(models.TextChoices):
    OWNER = "OWNER", "Owner"
    MANAGER = "MANAGER", "Manager"
    ACCOUNTANT = "ACCOUNTANT", "Accountant"
    CASHIER = "CASHIER", "Cashier"
    COUNTER_STAFF = "COUNTER_STAFF", "Counter Staff"
    STAFF = "STAFF", "Staff"


class EmploymentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ON_LEAVE = "ON_LEAVE", "On Leave"
    TERMINATED = "TERMINATED", "Terminated"


class Gender(models.TextChoices):
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"
    OTHER = "OTHER", "Other"


class IdProofType(models.TextChoices):
    AADHAAR = "AADHAAR", "Aadhaar"
    PAN = "PAN", "PAN"
    VOTER = "VOTER", "Voter ID"
    DRIVING = "DRIVING", "Driving License"
    PASSPORT = "PASSPORT", "Passport"
    OTHER = "OTHER", "Other"


class Employee(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee",
        help_text="Login account this employee profile belongs to.",
    )
    employee_code = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.STAFF, db_index=True)
    status = models.CharField(
        max_length=30,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        db_index=True,
    )

    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)

    personal_phone = models.CharField(max_length=15, blank=True)
    personal_email = models.EmailField(blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True)

    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)

    id_proof_type = models.CharField(max_length=20, choices=IdProofType.choices, blank=True)
    id_proof_number = models.CharField(max_length=50, blank=True)
    photo = models.ImageField(upload_to="employees/photos/", blank=True, null=True)
    notes = models.TextField(blank=True)

    #: Standard hourly wage used by the Daily Work Log to auto-credit salary.
    hourly_rate = money_field(default=0, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        indexes = [
            models.Index(fields=["role", "status"]),
        ]

    def __str__(self):
        return f"{self.employee_code} - {self.full_name}"

    def get_full_name(self) -> str:
        return self.full_name

    @property
    def is_supervisor(self) -> bool:
        """Owner and Manager share elevated responsibilities."""
        return self.role in (Role.OWNER, Role.MANAGER)
