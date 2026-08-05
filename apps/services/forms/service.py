"""Forms for the service catalog."""
from django import forms

from apps.services.models import Service, ServiceCategory


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "category", "unit", "price", "description"]
        widgets = {
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_price(self):
        value = self.cleaned_data["price"]
        if value is None or value <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return value


class ServiceFilterForm(forms.Form):
    category = forms.ChoiceField(
        choices=[("", "All categories")] + list(ServiceCategory.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
