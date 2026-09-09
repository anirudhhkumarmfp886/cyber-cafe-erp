"""Forms for the cash book."""
from django import forms

from apps.finance.models import BankAccount, CashBookEntry
from apps.finance.models.enums import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    CashEntryCategory,
    PaymentMode,
)


class CashBookEntryForm(forms.ModelForm):
    paid_from = forms.ChoiceField(
        choices=[
            ("SHOP_DRAWER", "Shop Cash Drawer (Main Galla)"),
            ("STAFF_FLOAT", "My Counter Cash Float (Staff Wallet)"),
        ],
        initial="SHOP_DRAWER",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_entry_paid_from"}),
        label="Paid From",
        help_text="For expense: choose whether paid from Shop Drawer or Staff Counter Float.",
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True).order_by("-is_default", "bank_name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_entry_bank_account"}),
        label="Bank Account (for UPI Book)",
        empty_label="Select Bank Account",
    )

    class Meta:
        model = CashBookEntry
        fields = ["entry_date", "entry_type", "category", "payment_mode", "amount", "party_name", "description"]
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "entry_type": forms.Select(attrs={"class": "form-select", "id": "id_entry_type"}),
            "category": forms.Select(attrs={"class": "form-select", "id": "id_entry_category"}),
            "payment_mode": forms.Select(attrs={"class": "form-select", "id": "id_entry_payment_mode"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "party_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Customer / vendor"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, allowed_entry_types=("INCOME", "EXPENSE"), **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("entry_type", "category", "payment_mode"):
            self.fields[name].widget.attrs["class"] = "form-select"
        self.fields["payment_mode"].initial = PaymentMode.CASH
        if allowed_entry_types:
            self.fields["entry_type"].choices = [
                (value, label)
                for value, label in self.fields["entry_type"].choices
                if value in allowed_entry_types
            ]
            self.fields["entry_type"].initial = allowed_entry_types[0]
        allowed_types = set(allowed_entry_types)
        if allowed_types == {"INCOME"}:
            self.fields["category"].choices = [
                (value, label)
                for value, label in CashEntryCategory.choices
                if value in INCOME_CATEGORIES
            ]
        elif allowed_types == {"EXPENSE"}:
            self.fields["category"].choices = [
                (value, label)
                for value, label in CashEntryCategory.choices
                if value in EXPENSE_CATEGORIES
            ]
        self.fields["entry_date"].required = False
        default_acc = BankAccount.objects.filter(is_default=True, is_active=True).first()
        if default_acc:
            self.fields["bank_account"].initial = default_acc

    def clean(self):
        cleaned = super().clean()
        entry_type = cleaned.get("entry_type")
        category = cleaned.get("category")
        payment_mode = cleaned.get("payment_mode") or PaymentMode.CASH
        cleaned["payment_mode"] = payment_mode
        bank_account = cleaned.get("bank_account")
        if entry_type and category:
            valid = INCOME_CATEGORIES if entry_type == "INCOME" else EXPENSE_CATEGORIES
            if category not in valid:
                raise forms.ValidationError(f"Category '{category}' is not valid for {entry_type} entries.")
        if cleaned.get("amount") is not None and cleaned["amount"] <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return cleaned



class OwnerCashForm(forms.Form):
    action = forms.ChoiceField(
        choices=[("DEPOSIT", "Deposit into Galla (Inflow)"), ("WITHDRAW", "Withdraw from Galla (Outflow)")],
        widget=forms.Select(attrs={"class": "form-select", "id": "id_owner_cash_action"}),
        label="Action",
    )
    source = forms.ChoiceField(
        choices=[
            ("", "-- Select Source / Channel --"),
            ("DIRECT", "Direct Cash (Pocket / Personal)"),
            ("BANK", "Bank Account (ATM / Transfer)"),
        ],
        required=True,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_owner_cash_source"}),
        label="Source / Channel",
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True).order_by("-is_default", "bank_name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_owner_cash_bank"}),
        label="Bank Account",
        empty_label="Select Bank Account",
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
        label="Amount",
    )
    payment_mode = forms.ChoiceField(
        choices=PaymentMode.choices,
        initial=PaymentMode.CASH,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Mode",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes / reference"}),
        label="Notes",
    )

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source")
        if not source:
            self.add_error("source", "Kripya Source / Channel select karein (Direct Cash ya Bank Account).")
        payment_mode = cleaned.get("payment_mode") or "CASH"
        cleaned["payment_mode"] = payment_mode
        bank_account = cleaned.get("bank_account")
        if source == "BANK" and not bank_account:
            self.add_error("bank_account", "Bank Transfer ke liye Bank Account select karna zaroori hai.")
        return cleaned




class CashBookFilterForm(forms.Form):
    entry_type = forms.ChoiceField(
        required=False,
        choices=[("", "All types"), ("INCOME", "Income"), ("EXPENSE", "Expense")],
        widget=forms.Select(attrs={"class": "form-select form-select-sm", "id": "id_filter_entry_type"}),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All categories")] + list(CashEntryCategory.choices),
        widget=forms.Select(attrs={"class": "form-select form-select-sm", "id": "id_filter_category"}),
    )
    from_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    to_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
