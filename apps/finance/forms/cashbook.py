"""Forms for the cash book."""
from django import forms

from apps.finance.models import CashBookEntry
from apps.finance.models.enums import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    CashEntryCategory,
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("entry_type", "category", "payment_mode"):
            self.fields[name].widget.attrs["class"] = "form-select"
        self.fields["entry_type"].initial = "INCOME"
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
