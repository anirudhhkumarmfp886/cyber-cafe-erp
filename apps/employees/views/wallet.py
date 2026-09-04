"""
Wallet views — thin CBVs delegating to WalletService / WalletSelector.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView

from apps.employees.forms.wallet import (
    WalletCreditForm,
    WalletDebitForm,
    WalletTopUpForm,
    WalletTransferForm,
)
from apps.employees.models import Wallet, WalletType
from apps.employees.selectors.wallet_selector import WalletSelector
from apps.employees.services.role_service import user_can_manage_topup
from apps.employees.services.wallet_service import WalletService


class WalletListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """All employees with their CASH + ONLINE wallet balances."""

    permission_required = "employees.view_wallettransaction"
    template_name = "employees/wallet_list.html"
    context_object_name = "rows"

    def get_queryset(self):
        return WalletSelector.list_employees_with_wallets()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Wallets"
        context["total_balance"] = WalletSelector.total_wallet_balance()
        return context


class WalletDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """A single wallet (CASH or ONLINE): ledger + credit / debit / top-up."""

    permission_required = "employees.view_wallettransaction"
    template_name = "employees/wallet_detail.html"
    context_object_name = "wallet"

    def get_object(self, queryset=None):
        return get_object_or_404(Wallet, id=self.kwargs["pk"])

    def _other_wallet(self, wallet):
        return WalletSelector.get_by_employee(
            wallet.employee,
            WalletType.ONLINE if wallet.wallet_type == WalletType.CASH else WalletType.CASH,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = self.object
        context["page_title"] = f"{wallet.get_wallet_type_display()} Wallet · {wallet.employee.full_name}"
        context["balance"] = WalletService.balance_of(wallet)
        context["transactions"] = WalletSelector.transactions(wallet, limit=150)
        context["other_wallet"] = self._other_wallet(wallet)
        can_topup = user_can_manage_topup(self.request.user)
        context["can_topup"] = can_topup
        if self.request.user.has_perm("employees.add_wallettransaction"):
            context["credit_form"] = WalletCreditForm()
            context["debit_form"] = WalletDebitForm()
            if can_topup:
                context["topup_form"] = WalletTopUpForm(wallet_type=wallet.wallet_type)
            context["transfer_form"] = WalletTransferForm(exclude_employee=wallet.employee)
        return context

    def post(self, request, pk):
        wallet = get_object_or_404(Wallet, id=pk)
        if not request.user.has_perm("employees.add_wallettransaction"):
            return self.handle_no_permission()

        action = request.POST.get("action")
        form = None
        try:
            if action == "topup":
                if not user_can_manage_topup(request.user):
                    messages.error(
                        request,
                        "Permission denied: Only the Owner or authorized staff with Top-Up access can fund wallets.",
                    )
                    return HttpResponseRedirect(reverse_lazy("employees:wallet_detail", kwargs={"pk": pk}))
                form = WalletTopUpForm(request.POST, wallet_type=wallet.wallet_type)
                if form.is_valid():
                    data = form.cleaned_data
                    WalletService.top_up(
                        employee=wallet.employee,
                        wallet_type=wallet.wallet_type,
                        amount=data["amount"],
                        bank_account=data.get("bank_account"),
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(
                        request,
                        f"Topped up ₹{data['amount']} to {wallet.employee.full_name}'s "
                        f"{wallet.get_wallet_type_display()} wallet.",
                    )
                else:
                    return self._form_error(request, wallet, "topup", form)
            elif action == "credit":
                form = WalletCreditForm(request.POST)
                if form.is_valid():
                    data = form.cleaned_data
                    WalletService.credit(
                        wallet=wallet,
                        amount=data["amount"],
                        category=data["category"],
                        source=data.get("source", ""),
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(request, f"Credited ₹{data['amount']} to {wallet.employee.full_name}'s wallet.")
                else:
                    return self._form_error(request, wallet, "credit", form)
            elif action == "debit":
                form = WalletDebitForm(request.POST)
                if form.is_valid():
                    data = form.cleaned_data
                    WalletService.debit(
                        wallet=wallet,
                        amount=data["amount"],
                        category=data["category"],
                        destination=data.get("destination", ""),
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(request, f"Debited ₹{data['amount']} from {wallet.employee.full_name}'s wallet.")
                else:
                    return self._form_error(request, wallet, "debit", form)
            elif action == "transfer":
                form = WalletTransferForm(request.POST, exclude_employee=wallet.employee)
                if form.is_valid():
                    data = form.cleaned_data
                    WalletService.transfer(
                        from_employee=wallet.employee,
                        to_employee=data["to_employee"],
                        amount=data["amount"],
                        wallet_type=wallet.wallet_type,
                        description=data.get("description", ""),
                        by=request.user,
                    )
                    messages.success(request, f"Transferred ₹{data['amount']} to {data['to_employee'].full_name}.")
                else:
                    return self._form_error(request, wallet, "transfer", form)
            else:
                messages.error(request, "Unknown wallet action.")
        except ValueError as exc:
            messages.error(request, str(exc))
            if form is not None:
                form.add_error(None, str(exc))
                return self._form_error(request, wallet, action, form)
        return HttpResponseRedirect(reverse_lazy("employees:wallet_detail", kwargs={"pk": wallet.pk}))

    def _form_error(self, request, wallet, action, form):
        """Re-render the detail page with the offending form bound and errors shown."""
        self.object = wallet
        context = self.get_context_data()
        can_topup = user_can_manage_topup(request.user)
        context["topup_form"] = (
            form if action == "topup"
            else (WalletTopUpForm(wallet_type=wallet.wallet_type) if can_topup else None)
        )
        context["credit_form"] = form if action == "credit" else WalletCreditForm()
        context["debit_form"] = form if action == "debit" else WalletDebitForm()
        context["transfer_form"] = (
            form if action == "transfer"
            else WalletTransferForm(exclude_employee=wallet.employee)
        )
        return self.render_to_response(context)
