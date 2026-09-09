"""Forms for customer creation and editing."""
from django import forms

from apps.customers.models import Customer
from apps.employees.services.role_service import user_can_manage_customer_credit


class CreditDepositForm(forms.Form):
    """Deposit or refund against a customer's pre-paid credit balance.

    Positive amount = deposit (customer pre-pays the shop); negative
    amount = refund (shop returns money to the customer).
    """

    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Amount (₹)"}),
    )
    direction = forms.ChoiceField(
        choices=(("DEPOSIT", "Deposit / Advance (+ Add to Customer Balance)"), ("REFUND", "Refund (- Return to Customer)")),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    payment_mode = forms.ChoiceField(
        choices=(
            ("CASH", "Cash (Received by Staff)"),
            ("STAFF_UPI", "Staff Personal UPI (Rush Hours / Bheed Mode)"),
            ("SHOP_UPI", "Shop UPI / QR (Direct Shop Bank)"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
        initial="CASH",
        required=False,
    )
    payment_destination = forms.ChoiceField(
        choices=(
            ("STAFF", "Staff Wallet (Credited to collecting staff daily hisaab)"),
            ("SHOP", "Shop Account (Direct to shop main galla / bank)"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
        initial="STAFF",
        required=False,
    )
    description = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Monthly photo copy advance / passport balance"}
        ),
    )


class CustomerForm(forms.ModelForm):
    credit_limit_reason = forms.CharField(
        required=False,
        label="Reason for Credit Limit Change",
        help_text="Optional note explaining why credit limit was set or changed.",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Regular trusted customer approved by Owner"}),
    )

    class Meta:
        model = Customer
        fields = [
            "full_name",
            "phone",
            "email",
            "gender",
            "date_of_birth",
            "credit_limit",
            "credit_limit_reason",
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user_can_manage_customer_credit(user):
            if "credit_limit" in self.fields:
                self.fields["credit_limit"].disabled = True
                self.fields["credit_limit"].help_text = (
                    "You do not have permission to change customer credit limits (Owner permission required)."
                )
            if "credit_limit_reason" in self.fields:
                self.fields["credit_limit_reason"].disabled = True

    def clean_credit_limit(self):
        value = self.cleaned_data.get("credit_limit")
        if value is not None and value < 0:
            raise forms.ValidationError("Credit limit cannot be negative.")
        return value
