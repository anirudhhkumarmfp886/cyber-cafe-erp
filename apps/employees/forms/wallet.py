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
        label="Amount (₹)",
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.none(),
        required=False,
        widget=forms.HiddenInput(),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Float distribution notes (optional)"}),
        label="Notes / Description",
    )

    def __init__(self, *args, wallet_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank_account"].queryset = BankAccount.objects.filter(is_active=True).order_by("account_name")
        self.fields["bank_account"].required = False
        self.fields["bank_account"].widget = forms.HiddenInput()


class WalletCreditForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    category = forms.ChoiceField(
        choices=[
            (WalletTransactionCategory.ADJUSTMENT, "Adjustment (Manual / Float)"),
            (WalletTransactionCategory.PAYMENT_COLLECTED, "Payment Collected (Customer / External)"),
            (WalletTransactionCategory.BONUS, "Bonus / Incentive"),
            (WalletTransactionCategory.SALARY, "Salary Payment"),
            (WalletTransactionCategory.CASH_TOPUP, "Direct Cash Top-up"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    source = forms.CharField(
        max_length=150,
        required=True,
        label="Source (Paisa kahan se aaya)",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Initial Counter Float, CSC Commission, Customer Advance"}
        ),
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
            (WalletTransactionCategory.ADJUSTMENT, "Adjustment (Manual / Drawer Return)"),
            (WalletTransactionCategory.EXPENSE, "Expense (Direct Cash Outflow)"),
            (WalletTransactionCategory.ADVANCE, "Advance Given"),
            (WalletTransactionCategory.CASH_WITHDRAWAL, "Cash Withdrawal"),
            (WalletTransactionCategory.PENALTY, "Penalty"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    destination = forms.CharField(
        max_length=150,
        required=True,
        label="Destination (Kahan / Kisko diya)",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Handed to Owner, Cash Drawer Return, Direct Expense"}
        ),
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


class WalletReturnFloatForm(forms.Form):
    """Staff returns daily counter float back to shop."""

    amount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
        label="Amount to Return (₹)",
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Daily evening float settlement notes (optional)"}),
        label="Notes / Settlement Remarks",
    )
