"""Forms for the service catalog."""
from django import forms

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
        fields = ["name", "category", "new_category", "unit", "price", "description"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["category"].required = False
        self.fields["category"].empty_label = "— Choose existing (or add new below) —"
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
