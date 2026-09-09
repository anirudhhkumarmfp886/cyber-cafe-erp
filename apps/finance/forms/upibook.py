"""Forms for the Shop UPI Book."""
from django import forms
from django.db import models

from apps.employees.models import Employee, EmploymentStatus
from apps.finance.models import BankAccount
from apps.finance.models.enums import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    CashEntryCategory,
    CashEntryType,
)


class UPIBookEntryForm(forms.Form):
    entry_type = forms.ChoiceField(
        choices=[
            (CashEntryType.INCOME, "UPI Inflow / Received (QR, Soundbox, Float In)"),
            (CashEntryType.EXPENSE, "UPI Outflow / Paid (Float Out, Vendor, Expense)"),
        ],
        initial=CashEntryType.INCOME,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_upi_entry_type"}),
        label="Entry Type",
    )
    category = forms.ChoiceField(
        choices=CashEntryCategory.choices,
        initial=CashEntryCategory.SALES,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_upi_category"}),
        label="Category",
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
        label="Amount (₹)",
    )
    party_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Customer / Vendor / Staff"}),
        label="Party Name / Payer",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "UPI UTR number, QR soundbox ref, or remarks"}),
        label="UPI Reference / Notes",
    )
    entry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Date",
    )

    def clean(self):
        cleaned_data = super().clean()
        entry_type = cleaned_data.get("entry_type")
        category = cleaned_data.get("category")
        if entry_type and category:
            valid_cats = INCOME_CATEGORIES if entry_type == CashEntryType.INCOME else EXPENSE_CATEGORIES
            if category not in valid_cats:
                self.add_error("category", f"Category '{category}' is not valid for {entry_type} entries.")
        return cleaned_data


class UPIBookFilterForm(forms.Form):
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True).order_by("-is_default", "account_name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
        label="Bank Account",
        empty_label="All Linked Accounts",
    )
    entry_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Types"), (CashEntryType.INCOME, "Inflow (Received)"), (CashEntryType.EXPENSE, "Outflow (Paid)")],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")] + list(CashEntryCategory.choices),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    from_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    to_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )


class OwnerUPIFloatForm(forms.Form):
    class Action(models.TextChoices):
        LOAD_FROM_BANK = "LOAD_FROM_BANK", "Transfer Float from Bank into UPI Book"
        SWEEP_TO_BANK = "SWEEP_TO_BANK", "Sweep Float / Profit from UPI Book to Bank"
        REIMBURSE_CASH = "REIMBURSE_CASH", "Reimburse Staff Cash Float from UPI Pool"

    action = forms.ChoiceField(
        choices=Action.choices,
        initial=Action.LOAD_FROM_BANK,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_owner_upi_action"}),
        label="Float Action",
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
        label="Amount (₹)",
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True).order_by("-is_default", "account_name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_owner_upi_bank"}),
        label="Shop Bank Account",
        empty_label="— Select Bank Account —",
    )
    staff = forms.ModelChoiceField(
        queryset=Employee.objects.filter(status=EmploymentStatus.ACTIVE).order_by("full_name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_owner_upi_staff"}),
        label="Staff (for Cash Reimbursement)",
        empty_label="— Shop Cash Drawer (Main Galla) —",
    )
    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Notes / Remarks"}),
        label="Description",
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        bank_account = cleaned_data.get("bank_account")
        if action in [self.Action.LOAD_FROM_BANK, self.Action.SWEEP_TO_BANK] and not bank_account:
            self.add_error("bank_account", "A bank account is required for transferring float to/from bank.")
        return cleaned_data
