"""Forms for customer creation and editing."""
from django import forms

from apps.customers.models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "full_name",
            "phone",
            "email",
            "gender",
            "date_of_birth",
            "credit_limit",
            "address_line",
            "city",
            "state",
            "pincode",
            "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "credit_limit": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def clean_credit_limit(self):
        value = self.cleaned_data["credit_limit"]
        if value is not None and value < 0:
            raise forms.ValidationError("Credit limit cannot be negative.")
        return value
