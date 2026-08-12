"""Forms for the cash book."""
from django import forms

from apps.finance.models import CashBookEntry
from apps.finance.models.enums import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    CashEntryCategory,
    PaymentMode,
)


class CashBookEntryForm(forms.ModelForm):
    class Meta:
        model = CashBookEntry
        fields = ["entry_date", "entry_type", "category", "payment_mode", "amount", "party_name", "description"]
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "party_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Customer / vendor"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, allowed_entry_types=("INCOME", "EXPENSE"), **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("entry_type", "category", "payment_mode"):
            self.fields[name].widget.attrs["class"] = "form-select"
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

    def clean(self):
        cleaned = super().clean()
        entry_type = cleaned.get("entry_type")
        category = cleaned.get("category")
        if entry_type and category:
            valid = INCOME_CATEGORIES if entry_type == "INCOME" else EXPENSE_CATEGORIES
            if category not in valid:
                raise forms.ValidationError(f"Category '{category}' is not valid for {entry_type} entries.")
        if cleaned.get("amount") is not None and cleaned["amount"] <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return cleaned


class OwnerCashForm(forms.Form):
    action = forms.ChoiceField(
        choices=[("WITHDRAW", "Owner Withdrawal"), ("DEPOSIT", "Owner Deposit")],
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Action",
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
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Mode",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        label="Notes",
    )


class CashBookFilterForm(forms.Form):
    entry_type = forms.ChoiceField(
        required=False,
        choices=[("", "All types"), ("INCOME", "Income"), ("EXPENSE", "Expense")],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All categories")] + list(CashEntryCategory.choices),
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
