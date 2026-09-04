"""Forms for the bank ledger."""
from django import forms

from apps.finance.models import BankAccount


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = [
            "account_name",
            "bank_name",
            "branch",
            "account_number",
            "ifsc_code",
            "account_type",
            "opening_balance",
            "is_default",
        ]
        widgets = {
            "account_name": forms.TextInput(attrs={"class": "form-control"}),
            "bank_name": forms.TextInput(attrs={"class": "form-control"}),
            "branch": forms.TextInput(attrs={"class": "form-control"}),
            "account_number": forms.TextInput(attrs={"class": "form-control"}),
            "ifsc_code": forms.TextInput(attrs={"class": "form-control"}),
            "account_type": forms.Select(attrs={"class": "form-select"}),
            "opening_balance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["opening_balance"].required = False
        self.fields["is_default"].label = "Set as default shop bank account (for UPI QR & general billing)"


class BankDepositForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    party_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Deposited by"}),
    )
    description = forms.CharField(
        max_length=500, required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class BankWithdrawalForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    party_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Paid to"}),
    )
    description = forms.CharField(
        max_length=500, required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class BankTransferForm(forms.Form):
    to_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.none(),
        label="Transfer to account",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    description = forms.CharField(
        max_length=500, required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, exclude_account=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = BankAccount.objects.all().order_by("account_name")
        if exclude_account:
            queryset = queryset.exclude(pk=exclude_account.pk)
        self.fields["to_account"].queryset = queryset
