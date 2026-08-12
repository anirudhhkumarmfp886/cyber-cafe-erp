"""Forms for wallet operations (credit, debit, transfer, top-up)."""
from django import forms

from apps.employees.models import Employee, WalletTransactionCategory, WalletType
from apps.finance.models import BankAccount


class WalletTopUpForm(forms.Form):
    """Owner funding of a staff wallet, mirrored in the shop ledgers."""

    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
        label="Amount",
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.none(),
        required=False,
        label="Source bank account",
        help_text="Required for ONLINE wallet top-up (owner transfers the money out).",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, wallet_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank_account"].queryset = BankAccount.objects.order_by("account_name")
        if wallet_type == WalletType.ONLINE:
            self.fields["bank_account"].required = True
        else:
            self.fields["bank_account"].widget = forms.HiddenInput()
            self.fields["bank_account"].help_text = ""


class WalletCreditForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    category = forms.ChoiceField(
        choices=[
            (WalletTransactionCategory.CASH_TOPUP, "Cash Top-up"),
            (WalletTransactionCategory.SALARY, "Salary Payment"),
            (WalletTransactionCategory.BONUS, "Bonus"),
            (WalletTransactionCategory.PAYMENT_COLLECTED, "Payment Collected"),
            (WalletTransactionCategory.ADJUSTMENT, "Adjustment"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    source = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Owner cash, Cash counter"}),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class WalletDebitForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    category = forms.ChoiceField(
        choices=[
            (WalletTransactionCategory.CASH_WITHDRAWAL, "Cash Withdrawal"),
            (WalletTransactionCategory.ADVANCE, "Advance"),
            (WalletTransactionCategory.PENALTY, "Penalty"),
            (WalletTransactionCategory.EXPENSE, "Expense"),
            (WalletTransactionCategory.ADJUSTMENT, "Adjustment"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    destination = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Cash counter, Party"}),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class WalletTransferForm(forms.Form):
    to_employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        label="Transfer to employee",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, exclude_employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Employee.objects.filter(is_active=True).order_by("full_name")
        if exclude_employee:
            queryset = queryset.exclude(pk=exclude_employee.pk)
        self.fields["to_employee"].queryset = queryset
