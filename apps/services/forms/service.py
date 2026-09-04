"""Forms for the service catalog."""
from django import forms

from apps.finance.models import BankAccount
from apps.services.models import Category, Service


class ServiceForm(forms.ModelForm):
    new_category = forms.CharField(
        required=False,
        max_length=50,
        label="New category",
        help_text="Optional: type a brand-new category if none of the existing ones fit.",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Cash Withdrawal",
            }
        ),
    )

    class Meta:
        model = Service
        fields = [
            "name",
            "category",
            "new_category",
            "unit",
            "price",
            "passthrough_type",
            "default_bank_account",
            "total_formula",
            "income_formula",
            "description",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "passthrough_type": forms.Select(attrs={"class": "form-select"}),
            "default_bank_account": forms.Select(attrs={"class": "form-select"}),
            "total_formula": forms.TextInput(
                attrs={
                    "class": "form-control font-monospace",
                    "placeholder": "e.g. cash * (1 + pct / 100)",
                }
            ),
            "income_formula": forms.TextInput(
                attrs={
                    "class": "form-control font-monospace",
                    "placeholder": "e.g. cash * pct / 100",
                }
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "default_bank_account": "Dedicated shop bank account for this service (e.g. AEPS CBI account). Leave blank to use the Shop Default UPI Account.",
            "total_formula": "Math formula for what the customer pays. Variables: qty, price, and the custom fields' variable names (e.g. cash, pct). Supports + - * / and parentheses.",
            "income_formula": "Math formula for what the shop keeps. Blank = same as the total. Never exceeds the total.",
            "passthrough_type": "How the difference between total and income leaves the shop. Blank = plain sale.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["category"].required = False
        self.fields["category"].empty_label = "— Choose existing (or add new below) —"
        self.fields["default_bank_account"].queryset = BankAccount.objects.filter(is_active=True).order_by("account_name")
        self.fields["default_bank_account"].required = False
        self.fields["default_bank_account"].empty_label = "— None (Uses Shop Default UPI Bank) —"
        self.fields["passthrough_type"].required = False
        if self.instance and self.instance.category_id:
            self.initial["category"] = self.instance.category_id

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        new_name = (cleaned.get("new_category") or "").strip()
        if category and new_name:
            self.add_error(
                "new_category",
                "Pick an existing category OR type a new one, not both.",
            )
        return cleaned

    def clean_price(self):
        value = self.cleaned_data["price"]
        if value is None or value <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return value


class ServiceFilterForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=Category.objects.order_by("name"),
        required=False,
        empty_label="All categories",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
