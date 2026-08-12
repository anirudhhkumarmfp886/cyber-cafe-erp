"""Cash book views."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView

from apps.employees.models import Employee, EmploymentStatus
from apps.finance.forms.cashbook import CashBookEntryForm, CashBookFilterForm, OwnerCashForm
from apps.finance.models import CashBookEntry
from apps.finance.selectors.cashbook_selector import CashBookSelector
from apps.finance.services.cashbook_service import CashBookService


class CashBookListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "finance.view_cashbookentry"
    template_name = "finance/cashbook_list.html"
    context_object_name = "entries"
    paginate_by = 25

    def can_view_shop(self):
        return self.request.user.is_superuser or self.request.user.has_perm("finance.withdraw_shop_cash")

    def effective_staff(self):
        """Non-privileged staff always see only their own cash book."""
        if self.can_view_shop():
            staff_id = self.request.GET.get("staff")
            if staff_id:
                return get_object_or_404(Employee, id=staff_id)
            return None
        return getattr(self.request.user, "employee", None)

    def get_queryset(self):
        form = CashBookFilterForm(self.request.GET)
        filters = {"staff": self.effective_staff()}
        if form.is_valid():
            filters.update(
                {
                    "entry_type": form.cleaned_data.get("entry_type"),
                    "category": form.cleaned_data.get("category"),
                    "from_date": form.cleaned_data.get("from_date"),
                    "to_date": form.cleaned_data.get("to_date"),
                    "q": self.request.GET.get("q", ""),
                }
            )
        return CashBookSelector.list_entries(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.effective_staff()
        request = self.request
        context["page_title"] = "Cash Book"
        context["filter_form"] = CashBookFilterForm(request.GET)
        context["staff"] = staff
        context["staff_label"] = staff.get_full_name() if staff else "Shop Cash Book"
        context["can_view_shop"] = self.can_view_shop()
        context["staff_list"] = Employee.objects.filter(
            status=EmploymentStatus.ACTIVE
        ).order_by("full_name") if self.can_view_shop() else []
        context["balance"] = CashBookSelector.balance(staff=staff)
        context["income_total"] = CashBookSelector.income_total(staff=staff)
        context["expense_total"] = CashBookSelector.expense_total(staff=staff)
        today = date.today()
        context["today"] = today
        context["today_income"] = CashBookSelector.income_total(from_date=today, to_date=today, staff=staff)
        context["today_expense"] = CashBookSelector.expense_total(from_date=today, to_date=today, staff=staff)
        context["today_net"] = context["today_income"] - context["today_expense"]
        as_on = request.GET.get("as_on")
        try:
            as_on_date = date.fromisoformat(as_on) if as_on else today
        except ValueError:
            as_on_date = today
        context["as_on"] = as_on_date
        context["as_on_balance"] = CashBookSelector.balance_on(as_on_date, staff=staff)

        can_add_income = request.user.has_perm("finance.add_cashbookincome")
        can_add_expense = request.user.has_perm("finance.add_cashbookexpense")
        context["can_add_income"] = can_add_income
        context["can_add_expense"] = can_add_expense
        allowed_types = []
        if can_add_income:
            allowed_types.append("INCOME")
        if can_add_expense:
            allowed_types.append("EXPENSE")
        if allowed_types:
            context["entry_form"] = CashBookEntryForm(allowed_entry_types=tuple(allowed_types))
        context["owner_cash_form"] = OwnerCashForm() if request.user.has_perm("finance.withdraw_shop_cash") else None
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["entry_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("finance.add_cashbookentry"):
            return self.handle_no_permission()
        allowed_types = []
        if request.user.has_perm("finance.add_cashbookincome"):
            allowed_types.append("INCOME")
        if request.user.has_perm("finance.add_cashbookexpense"):
            allowed_types.append("EXPENSE")
        if not allowed_types:
            return self.handle_no_permission()
        form = CashBookEntryForm(request.POST, allowed_entry_types=tuple(allowed_types))
        if form.is_valid():
            data = form.cleaned_data
            try:
                if data["entry_type"] == "INCOME":
                    entry = CashBookService.record_income(
                        amount=data["amount"],
                        category=data["category"],
                        payment_mode=data["payment_mode"],
                        party_name=data.get("party_name", ""),
                        description=data.get("description", ""),
                        entry_date=data.get("entry_date"),
                        by=request.user,
                    )
                else:
                    entry = CashBookService.record_expense(
                        amount=data["amount"],
                        category=data["category"],
                        payment_mode=data["payment_mode"],
                        party_name=data.get("party_name", ""),
                        description=data.get("description", ""),
                        entry_date=data.get("entry_date"),
                        by=request.user,
                    )
                messages.success(request, f"Recorded {entry.entry_type.lower()} {entry.reference_number}.")
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
        else:
            return self.get_form_error_response(form)
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))


class OwnerCashView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.withdraw_shop_cash"
    http_method_names = ["post"]

    def post(self, request):
        form = OwnerCashForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                if data["action"] == "WITHDRAW":
                    entry = CashBookService.owner_withdraw(
                        amount=data["amount"],
                        payment_mode=data["payment_mode"],
                        description=data.get("description", ""),
                        by=request.user,
                    )
                else:
                    entry = CashBookService.owner_deposit(
                        amount=data["amount"],
                        payment_mode=data["payment_mode"],
                        description=data.get("description", ""),
                        by=request.user,
                    )
                messages.success(
                    request,
                    f"{'Withdrew' if data['action'] == 'WITHDRAW' else 'Deposited'} "
                    f"{entry.amount} ({entry.reference_number}).",
                )
            except ValueError as exc:
                messages.error(request, str(exc))
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))


class CashBookDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.delete_cashbookentry"
    http_method_names = ["post"]

    def post(self, request, pk):
        entry = get_object_or_404(CashBookEntry, id=pk)
        CashBookService.soft_delete_entry(entry, by=request.user)
        messages.success(request, f"Entry {entry.reference_number} deleted (soft).")
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))
