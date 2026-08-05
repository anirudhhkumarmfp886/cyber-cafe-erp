"""Filter forms for the report pages."""
from django import forms

from apps.employees.models import Employee
from apps.finance.models import BankAccount


class DateRangeForm(forms.Form):
    from_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    to_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )


class BankStatementForm(DateRangeForm):
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.order_by("account_name"),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )


class WalletStatementForm(DateRangeForm):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.order_by("full_name"),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )


class CustomerLedgerForm(DateRangeForm):
    customer = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.customers.models import Customer

        self.fields["customer"].queryset = Customer.objects.order_by("full_name")
        self.fields["customer"].empty_label = "All customers"
