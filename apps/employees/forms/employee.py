"""Forms for employee creation and editing."""
from django import forms
from django.contrib.auth import get_user_model

from apps.employees.models import Employee
from apps.employees.services.role_service import user_can_manage_permissions

User = get_user_model()


class EmployeeCreateForm(forms.ModelForm):
    """Combines login credentials with the employee HR profile.

    Validation is split across layers:
      1. Model constraints (unique employee_code, choices)
      2. Form validation (username uniqueness, password confirmation)
      3. Service validation (EmployeeService guards the same rules again)
    """

    username = forms.CharField(max_length=150)
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    can_create_bills = forms.BooleanField(
        required=False,
        label="Billing Access (Can Create Bills)",
        help_text="Allow this employee to create bills and counter invoices regardless of base role.",
    )
    can_manage_topup = forms.BooleanField(
        required=False,
        label="Top-Up & Owner Cash Access",
        help_text="Allow this employee to perform wallet top-ups and owner cash deposit/withdrawal.",
    )
    can_record_expenses = forms.BooleanField(
        required=False,
        label="Expense Recording Access (Can Record Expenses)",
        help_text="Allow this employee to record shop expenses from counter float or shop bank.",
    )
    can_collect_personal_upi = forms.BooleanField(
        required=False,
        label="Personal UPI Collection Access",
        help_text="Allow staff to collect payments into their personal Staff UPI/Wallet during rush hours.",
    )
    can_view_shop_finance = forms.BooleanField(
        required=False,
        label="Entire Shop Galla & UPI Access",
        help_text="Allow staff to view entire shop cashbook (main galla) and shop UPI books.",
    )
    can_manage_permissions = forms.BooleanField(
        required=False,
        label="Permission Management Access",
        help_text="Allow this employee to assign and modify permissions for other staff.",
    )
    can_manage_customer_credit = forms.BooleanField(
        required=False,
        label="Customer Credit Management Access",
        help_text="Allow this employee to set and modify customer credit limits.",
    )

    class Meta:
        model = Employee
        fields = [
            "full_name",
            "role",
            "status",
            "can_create_bills",
            "can_manage_topup",
            "can_record_expenses",
            "can_collect_personal_upi",
            "can_view_shop_finance",
            "can_manage_permissions",
            "can_manage_customer_credit",
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
            "hourly_rate",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "date_of_joining": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user_can_manage_permissions(user):
            for field_name in [
                "can_create_bills",
                "can_manage_topup",
                "can_record_expenses",
                "can_collect_personal_upi",
                "can_view_shop_finance",
                "can_manage_permissions",
                "can_manage_customer_credit",
                "role",
            ]:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


class EmployeeUpdateForm(forms.ModelForm):
    """Editing an employee; credentials are managed separately."""

    can_create_bills = forms.BooleanField(
        required=False,
        label="Billing Access (Can Create Bills)",
        help_text="Allow this employee to create bills and counter invoices regardless of base role.",
    )
    can_manage_topup = forms.BooleanField(
        required=False,
        label="Top-Up & Owner Cash Access",
        help_text="Allow this employee to perform wallet top-ups and owner cash deposit/withdrawal.",
    )
    can_record_expenses = forms.BooleanField(
        required=False,
        label="Expense Recording Access (Can Record Expenses)",
        help_text="Allow this employee to record shop expenses from counter float or shop bank.",
    )
    can_collect_personal_upi = forms.BooleanField(
        required=False,
        label="Personal UPI Collection Access",
        help_text="Allow staff to collect payments into their personal Staff UPI/Wallet during rush hours.",
    )
    can_view_shop_finance = forms.BooleanField(
        required=False,
        label="Entire Shop Galla & UPI Access",
        help_text="Allow staff to view entire shop cashbook (main galla) and shop UPI books.",
    )
    can_manage_permissions = forms.BooleanField(
        required=False,
        label="Permission Management Access",
        help_text="Allow this employee to assign and modify permissions for other staff.",
    )
    can_manage_customer_credit = forms.BooleanField(
        required=False,
        label="Customer Credit Management Access",
        help_text="Allow this employee to set and modify customer credit limits.",
    )

    class Meta:
        model = Employee
        fields = [
            "full_name",
            "role",
            "status",
            "can_create_bills",
            "can_manage_topup",
            "can_record_expenses",
            "can_collect_personal_upi",
            "can_view_shop_finance",
            "can_manage_permissions",
            "can_manage_customer_credit",
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
            "hourly_rate",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "date_of_joining": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user_can_manage_permissions(user):
            for field_name in [
                "can_create_bills",
                "can_manage_topup",
                "can_record_expenses",
                "can_collect_personal_upi",
                "can_view_shop_finance",
                "can_manage_permissions",
                "can_manage_customer_credit",
                "role",
            ]:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True



