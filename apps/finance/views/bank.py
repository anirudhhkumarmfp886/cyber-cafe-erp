"""Bank ledger views."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView

from apps.finance.forms.bank import (
    BankAccountForm,
    BankDepositForm,
    BankTransferForm,
    BankWithdrawalForm,
)
from apps.finance.models import BankAccount
from apps.finance.selectors.bank_selector import BankSelector
from apps.finance.services.bank_service import BankService


class BankAccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "finance.view_bankaccount"
    template_name = "finance/bank_list.html"
    context_object_name = "accounts"
    paginate_by = 25

    def get_queryset(self):
        return BankSelector.list_accounts()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Bank Accounts"
        context["total_balance"] = BankSelector.total_balance()
        if self.request.user.has_perm("finance.add_bankaccount"):
            context["account_form"] = BankAccountForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["account_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("finance.add_bankaccount"):
            return self.handle_no_permission()
        form = BankAccountForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                account = BankService.create_account(
                    account_name=data["account_name"],
                    bank_name=data["bank_name"],
                    account_number=data["account_number"],
                    ifsc_code=data.get("ifsc_code", ""),
                    branch=data.get("branch", ""),
                    account_type=data["account_type"],
                    opening_balance=data.get("opening_balance") or 0,
                    is_default=data.get("is_default", False),
                    by=request.user,
                )
                messages.success(request, f"Account {account.account_name} created.")
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
        else:
            return self.get_form_error_response(form)
        return HttpResponseRedirect(reverse_lazy("finance:bank_list"))


class SetDefaultBankAccountView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.change_bankaccount"

    def post(self, request, pk):
        account = get_object_or_404(BankAccount, id=pk)
        BankService.set_default_account(account, by=request.user)
        messages.success(request, f"'{account.account_name}' ({account.bank_name}) is now the default shop bank account.")
        return HttpResponseRedirect(reverse_lazy("finance:bank_list"))


class BankAccountDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "finance.view_bankaccount"
    template_name = "finance/bank_detail.html"
    context_object_name = "account"

    def get_object(self, queryset=None):
        return get_object_or_404(BankAccount, id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.object
        context["page_title"] = f"Bank · {account.account_name}"
        context["balance"] = BankService.balance_of(account)
        context["transactions"] = BankSelector.transactions(account, limit=150)
        if self.request.user.has_perm("finance.add_banktransaction"):
            context["deposit_form"] = BankDepositForm()
            context["withdrawal_form"] = BankWithdrawalForm()
            context["transfer_form"] = BankTransferForm(exclude_account=account)
        return context

    def post(self, request, pk):
        account = get_object_or_404(BankAccount, id=pk)
        if not request.user.has_perm("finance.add_banktransaction"):
            return self.handle_no_permission()

        action = request.POST.get("action")
        form = None
        try:
            if action == "deposit":
                form = BankDepositForm(request.POST)
                if form.is_valid():
                    data = form.cleaned_data
                    BankService.deposit(
                        account=account,
                        amount=data["amount"],
                        party_name=data.get("party_name", ""),
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(request, f"Deposited ₹{data['amount']} to {account.account_name}.")
                else:
                    return self._form_error(request, account, "deposit", form)
            elif action == "withdraw":
                form = BankWithdrawalForm(request.POST)
                if form.is_valid():
                    data = form.cleaned_data
                    BankService.withdraw(
                        account=account,
                        amount=data["amount"],
                        party_name=data.get("party_name", ""),
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(request, f"Withdrew ₹{data['amount']} from {account.account_name}.")
                else:
                    return self._form_error(request, account, "withdraw", form)
            elif action == "transfer":
                form = BankTransferForm(request.POST, exclude_account=account)
                if form.is_valid():
                    data = form.cleaned_data
                    BankService.transfer(
                        from_account=account,
                        to_account=data["to_account"],
                        amount=data["amount"],
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(request, f"Transferred ₹{data['amount']} to {data['to_account'].account_name}.")
                else:
                    return self._form_error(request, account, "transfer", form)
            else:
                messages.error(request, "Unknown bank action.")
        except ValueError as exc:
            messages.error(request, str(exc))
            if form is not None:
                form.add_error(None, str(exc))
                return self._form_error(request, account, action, form)
        return HttpResponseRedirect(reverse_lazy("finance:bank_detail", kwargs={"pk": account.pk}))

    def _form_error(self, request, account, action, form):
        self.object = account
        context = self.get_context_data()
        context["deposit_form"] = form if action == "deposit" else BankDepositForm()
        context["withdrawal_form"] = form if action == "withdraw" else BankWithdrawalForm()
        context["transfer_form"] = form if action == "transfer" else BankTransferForm(exclude_account=account)
        return self.render_to_response(context)
