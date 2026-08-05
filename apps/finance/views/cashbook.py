"""Cash book views."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView

from apps.finance.forms.cashbook import CashBookEntryForm, CashBookFilterForm
from apps.finance.models import CashBookEntry
from apps.finance.selectors.cashbook_selector import CashBookSelector
from apps.finance.services.cashbook_service import CashBookService


class CashBookListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "finance.view_cashbookentry"
    template_name = "finance/cashbook_list.html"
    context_object_name = "entries"
    paginate_by = 25

    def get_queryset(self):
        form = CashBookFilterForm(self.request.GET)
        filters = {}
        if form.is_valid():
            filters = {
                "entry_type": form.cleaned_data.get("entry_type"),
                "category": form.cleaned_data.get("category"),
                "from_date": form.cleaned_data.get("from_date"),
                "to_date": form.cleaned_data.get("to_date"),
                "q": self.request.GET.get("q", ""),
            }
        return CashBookSelector.list_entries(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Cash Book"
        context["filter_form"] = CashBookFilterForm(self.request.GET)
        context["balance"] = CashBookSelector.balance()
        context["income_total"] = CashBookSelector.income_total()
        context["expense_total"] = CashBookSelector.expense_total()
        if self.request.user.has_perm("finance.add_cashbookentry"):
            context["entry_form"] = CashBookEntryForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["entry_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("finance.add_cashbookentry"):
            return self.handle_no_permission()
        form = CashBookEntryForm(request.POST)
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


class CashBookDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.delete_cashbookentry"
    http_method_names = ["post"]

    def post(self, request, pk):
        entry = get_object_or_404(CashBookEntry, id=pk)
        CashBookService.soft_delete_entry(entry, by=request.user)
        messages.success(request, f"Entry {entry.reference_number} deleted (soft).")
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))
