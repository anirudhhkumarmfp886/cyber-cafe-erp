"""Forms for employee creation and editing."""
from django import forms
from django.contrib.auth import get_user_model

from apps.employees.models import Employee

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

    class Meta:
        model = Employee
        fields = [
            "full_name",
            "role",
            "status",
            "can_create_bills",
            "can_manage_topup",
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

    class Meta:
        model = Employee
        fields = [
            "full_name",
            "role",
            "status",
            "can_create_bills",
            "can_manage_topup",
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


