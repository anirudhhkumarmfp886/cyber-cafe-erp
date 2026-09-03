"""Forms for inventory management."""
from django import forms

from apps.finance.models.enums import PaymentMode
from apps.inventory.models import StockItem
from apps.inventory.models.enums import MovementType, OUTBOUND_TYPES


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = [
            "name",
            "sku",
            "category",
            "unit",
            "reorder_level",
            "description",
        ]
        widgets = {
            "reorder_level": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_reorder_level(self):
        value = self.cleaned_data.get("reorder_level")
        if value is not None and value < 0:
            raise forms.ValidationError("Reorder level cannot be negative.")
        return value


class StockInForm(forms.Form):
    """Purchase / stock-in form."""

    quantity = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    unit_cost = forms.DecimalField(
        min_value=0,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Cost per unit for this purchase.",
    )
    supplier_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Supplier / vendor name"}),
    )
    movement_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Leave blank for today.",
    )
    payment_mode = forms.ChoiceField(
        choices=[("", "— No cash book entry —")] + list(PaymentMode.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select a mode to auto-book a PURCHASE expense in the cash book.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes"}),
    )


class StockOutForm(forms.Form):
    """Issue / damage / return form."""

    quantity = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    movement_type = forms.ChoiceField(
        choices=[(k, v) for k, v in MovementType.choices if k in OUTBOUND_TYPES],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Issued to Counter 1, Damaged in transit"}
        ),
    )
    movement_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Leave blank for today.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes"}),
    )


class AdjustmentForm(forms.Form):
    """Physical count adjustment form."""

    new_quantity = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Enter the actual physical count.",
    )
    reason = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Physical count mismatch, Correction"}
        ),
    )
