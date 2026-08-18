"""Forms for service custom-field definitions (owner-managed)."""
from django import forms

from apps.employees.models import Role
from apps.services.models import ServiceCustomField


class ServiceCustomFieldForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        choices=Role.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Allowed roles",
        help_text="Which staff roles can see and fill this field. Leave blank for everyone.",
    )

    class Meta:
        model = ServiceCustomField
        fields = ["label", "variable_name", "field_type", "required", "help_text", "ordering"]
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "variable_name": forms.TextInput(
                attrs={
                    "class": "form-control font-monospace",
                    "placeholder": "auto from label, e.g. cash_amount",
                }
            ),
            "field_type": forms.Select(attrs={"class": "form-select"}),
            "required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "help_text": forms.TextInput(attrs={"class": "form-control"}),
            "ordering": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["help_text"].required = False
        self.fields["ordering"].required = False
        self.fields["variable_name"].required = False
