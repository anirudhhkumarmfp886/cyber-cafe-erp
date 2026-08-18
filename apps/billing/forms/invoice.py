"""Forms for billing: invoices (header + lines) and settlements."""
from django import forms

from apps.billing.models import Invoice, InvoiceLine, InvoicePaymentMode
from apps.customers.models import Customer
from apps.finance.models import BankAccount
from apps.services.models import Service


class InvoiceForm(forms.ModelForm):
    customer_name = forms.CharField(
        required=False,
        max_length=150,
        label="Customer name (new)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Name if not listed above"}),
    )
    create_customer = forms.BooleanField(
        required=False,
        label="Save as a new customer",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Invoice
        fields = ["customer", "customer_name", "create_customer", "payment_mode", "discount", "notes"]
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

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        customer_name = (cleaned.get("customer_name") or "").strip()
        create_customer = cleaned.get("create_customer")
        if customer and customer_name:
            self.add_error("customer_name", "Either pick a customer from the list or type a new name, not both.")
        if create_customer and not customer_name:
            self.add_error("customer_name", "Enter a name to save a new customer.")
        return cleaned

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


class PaymentSplitForm(forms.Form):
    mode = forms.ChoiceField(
        choices=[(mode.value, mode.label) for mode in InvoicePaymentMode if mode.value != "CREDIT"],
        initial=InvoicePaymentMode.UPI,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0", "placeholder": "0.00"}
        ),
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.order_by("account_name"),
        required=False,
        empty_label="Shop bank account (UPI / bank)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )


PaymentSplitFormSet = forms.formset_factory(PaymentSplitForm, extra=2)


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
