"""Forms for billing: invoices (header + lines) and cash-outs."""
from django import forms

from apps.billing.models import CashOut, Invoice, InvoiceLine, InvoicePaymentMode
from apps.customers.models import Customer
from apps.finance.models import BankAccount
from apps.services.models import Service


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["customer", "payment_mode", "discount", "notes"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "payment_mode": forms.Select(attrs={"class": "form-select"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "0.00"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.order_by("full_name")
        self.fields["customer"].required = False

    def clean_discount(self):
        value = self.cleaned_data["discount"]
        if value is None:
            return 0
        if value < 0:
            raise forms.ValidationError("Discount cannot be negative.")
        return value


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = ["service", "qty"]
        widgets = {
            "service": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "qty": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.order_by("category", "name")
        self.fields["service"].empty_label = "Select a service..."

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("qty")
        if cleaned.get("service") and qty is not None and qty <= 0:
            self.add_error("qty", "Quantity must be greater than zero.")
        return cleaned


InvoiceLineFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceLine,
    form=InvoiceLineForm,
    extra=3,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class SettleInvoiceForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
    )
    payment_mode = forms.ChoiceField(
        choices=[(mode, mode.label) for mode in InvoicePaymentMode if mode.value != "CREDIT"],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class CashOutForm(forms.ModelForm):
    class Meta:
        model = CashOut
        fields = ["customer", "bank_account", "transfer_amount", "commission_percent", "notes"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "bank_account": forms.Select(attrs={"class": "form-select"}),
            "transfer_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "commission_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.order_by("full_name")
        self.fields["customer"].required = False
        self.fields["bank_account"].queryset = BankAccount.objects.order_by("account_name")
        self.fields["commission_percent"].initial = 0
