"""Forms for work entries (counter page + editable bill)."""
from django import forms

from apps.customers.models import Customer
from apps.finance.models import BankAccount
from apps.services.models import Service
from apps.workentry.models import WorkEntry, WorkPaymentMode


class WorkEntryForm(forms.ModelForm):
    customer_name = forms.CharField(
        required=False,
        max_length=150,
        label="Customer name (new / walk-in)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Leave blank if not needed"}),
    )

    class Meta:
        model = WorkEntry
        fields = [
            "entry_date",
            "customer",
            "customer_name",
            "service",
            "page_quantity",
            "charged_amount",
            "payment_mode",
            "credit_rest_mode",
            "bank_account",
            "transfer_to_customer",
            "transfer_on_behalf",
            "cash_withdrawal",
            "notes",
        ]
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "customer": forms.Select(attrs={"class": "form-select"}),
            "service": forms.Select(attrs={"class": "form-select"}),
            "page_quantity": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "charged_amount": forms.NumberInput(
                attrs={"class": "form-control work-money", "step": "0.01", "min": "0"}
            ),
            "payment_mode": forms.Select(attrs={"class": "form-select", "id": "id_work_payment_mode"}),
            "credit_rest_mode": forms.Select(attrs={"class": "form-select"}),
            "bank_account": forms.Select(attrs={"class": "form-select"}),
            "transfer_to_customer": forms.NumberInput(
                attrs={"class": "form-control work-money", "step": "0.01", "min": "0"}
            ),
            "transfer_on_behalf": forms.NumberInput(
                attrs={"class": "form-control work-money", "step": "0.01", "min": "0"}
            ),
            "cash_withdrawal": forms.NumberInput(
                attrs={"class": "form-control work-money", "step": "0.01", "min": "0"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.order_by("full_name")
        self.fields["customer"].required = False
        self.fields["entry_date"].required = False
        self.fields["entry_date"].initial = None
        self.fields["charged_amount"].required = False
        self.fields["transfer_to_customer"].required = False
        self.fields["transfer_on_behalf"].required = False
        self.fields["cash_withdrawal"].required = False
        self.fields["page_quantity"].required = False
        self.fields["service"].queryset = Service.objects.order_by("category__name", "name")
        self.fields["service"].empty_label = "Select a service..."
        self.fields["bank_account"].queryset = BankAccount.objects.order_by("account_name")
        self.fields["bank_account"].required = False
        self.fields["bank_account"].empty_label = "Shop bank / UPI account (for online payments)"
        self.fields["credit_rest_mode"].required = False
        self.fields["credit_rest_mode"].empty_label = "— How rest is paid —"
        self.fields["charged_amount"].initial = 0
        self.fields["page_quantity"].initial = 0
        self.fields["transfer_to_customer"].initial = 0
        self.fields["transfer_on_behalf"].initial = 0
        self.fields["cash_withdrawal"].initial = 0

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        customer_name = (cleaned.get("customer_name") or "").strip()
        if customer and customer_name:
            self.add_error("customer_name", "Either pick a customer from the list or type a new name, not both.")

        def _amount(name):
            value = cleaned.get(name) or 0
            if value < 0:
                self.add_error(name, "Cannot be negative.")
            return value

        charged = _amount("charged_amount")
        transfer_to_customer = _amount("transfer_to_customer")
        transfer_on_behalf = _amount("transfer_on_behalf")
        cash_withdrawal = _amount("cash_withdrawal")

        page_qty = cleaned.get("page_quantity")
        if page_qty is not None and page_qty < 0:
            self.add_error("page_quantity", "Cannot be negative.")

        total = charged + transfer_to_customer + transfer_on_behalf + cash_withdrawal
        if total <= 0:
            self.add_error(
                None,
                "Enter at least one amount — charged amount, a transfer or a cash withdrawal.",
            )

        mode = cleaned.get("payment_mode")
        if mode in (WorkPaymentMode.UPI, WorkPaymentMode.CARD, WorkPaymentMode.BANK_TRANSFER):
            if not cleaned.get("bank_account"):
                self.add_error("bank_account", "Select the shop bank / UPI account receiving this payment.")
        elif mode == WorkPaymentMode.CUSTOMER_CREDIT:
            if customer is None:
                self.add_error("customer", "Customer credit requires a customer.")
            else:
                credit_balance = customer.credit_balance
                settled = min(total, credit_balance)
                rest = total - settled
                if rest > 0:
                    rest_mode = cleaned.get("credit_rest_mode")
                    if not rest_mode:
                        self.add_error(
                            "credit_rest_mode",
                            f"Credit covers {settled}; choose how the remaining {rest} is paid.",
                        )
                    elif rest_mode in (WorkPaymentMode.UPI, WorkPaymentMode.CARD, WorkPaymentMode.BANK_TRANSFER):
                        if not cleaned.get("bank_account"):
                            self.add_error("bank_account", "Select the shop bank / UPI account for the rest payment.")
        return cleaned
