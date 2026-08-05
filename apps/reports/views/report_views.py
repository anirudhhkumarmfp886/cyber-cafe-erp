"""
Report views — read-only pages plus CSV export.

Every report defaults to the last 30 days, accepts a date-range filter form,
and returns a downloadable CSV when ``?export=csv`` is present.
"""
from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import TemplateView

from apps.employees.models import Employee
from apps.finance.models import BankAccount
from apps.reports.forms.report_forms import (
    BankStatementForm,
    CustomerLedgerForm,
    DateRangeForm,
    WalletStatementForm,
)
from apps.reports.services.report_service import ReportService


def _default_range():
    return date.today() - timedelta(days=30), date.today()


def _valid_form(form_class, request):
    """Bind + validate; callers read cleaned_data only when is_valid()."""
    form = form_class(request.GET)
    form.is_valid()
    return form


def _resolve_range(form):
    if not form.is_valid():
        return _default_range()
    from_date = form.cleaned_data.get("from_date") or _default_range()[0]
    to_date = form.cleaned_data.get("to_date") or date.today()
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def _pick(form, field, fallback):
    if form.is_valid() and form.cleaned_data.get(field):
        return form.cleaned_data[field]
    return fallback()


class ReportIndexView(LoginRequiredMixin, TemplateView):
    template_name = "reports/report_index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Reports & Analytics"
        return context


class ProfitLossView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "finance.view_cashbookentry"
    template_name = "reports/profit_loss.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _valid_form(DateRangeForm, self.request)
        from_date, to_date = _resolve_range(form)
        context.update(
            {
                "page_title": "Profit & Loss",
                "form": form,
                "from_date": from_date,
                "to_date": to_date,
                "data": ReportService.profit_loss(from_date, to_date),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            form = _valid_form(DateRangeForm, request)
            from_date, to_date = _resolve_range(form)
            data = ReportService.profit_loss(from_date, to_date)
            return ReportService.profit_loss_csv(data, from_date, to_date)
        return super().get(request, *args, **kwargs)


class BankStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "finance.view_bankaccount"
    template_name = "reports/bank_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _valid_form(BankStatementForm, self.request)
        account = _pick(form, "bank_account", lambda: BankAccount.objects.first())
        from_date, to_date = _resolve_range(form)
        context.update(
            {
                "page_title": "Bank Statement",
                "form": form,
                "account": account,
                "from_date": from_date,
                "to_date": to_date,
                "data": ReportService.bank_statement(account, from_date, to_date)
                if account
                else None,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            form = _valid_form(BankStatementForm, request)
            account = _pick(form, "bank_account", lambda: BankAccount.objects.first())
            from_date, to_date = _resolve_range(form)
            data = ReportService.bank_statement(account, from_date, to_date)
            return ReportService.bank_statement_csv(data, account.account_name, from_date, to_date)
        return super().get(request, *args, **kwargs)


class CustomerLedgerView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "billing.view_invoice"
    template_name = "reports/customer_ledger.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _valid_form(CustomerLedgerForm, self.request)
        customer = _pick(form, "customer", lambda: None)
        from_date, to_date = _resolve_range(form)
        context.update(
            {
                "page_title": "Customer Ledger",
                "form": form,
                "from_date": from_date,
                "to_date": to_date,
                "data": ReportService.customer_ledger(
                    from_date, to_date, customer.id if customer else None
                ),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            form = _valid_form(CustomerLedgerForm, request)
            customer = _pick(form, "customer", lambda: None)
            from_date, to_date = _resolve_range(form)
            data = ReportService.customer_ledger(
                from_date, to_date, customer.id if customer else None
            )
            return ReportService.customer_ledger_csv(data, from_date, to_date)
        return super().get(request, *args, **kwargs)


class WalletStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "employees.view_wallettransaction"
    template_name = "reports/wallet_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _valid_form(WalletStatementForm, self.request)
        employee = _pick(form, "employee", lambda: Employee.objects.first())
        from_date, to_date = _resolve_range(form)
        context.update(
            {
                "page_title": "Wallet Statement",
                "form": form,
                "employee": employee,
                "from_date": from_date,
                "to_date": to_date,
                "data": ReportService.wallet_statement(employee, from_date, to_date)
                if employee
                else None,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            form = _valid_form(WalletStatementForm, request)
            employee = _pick(form, "employee", lambda: Employee.objects.first())
            from_date, to_date = _resolve_range(form)
            data = ReportService.wallet_statement(employee, from_date, to_date)
            return ReportService.wallet_statement_csv(data, employee.full_name, from_date, to_date)
        return super().get(request, *args, **kwargs)


class SalarySummaryView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "employees.view_worklogentry"
    template_name = "reports/salary_summary.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _valid_form(DateRangeForm, self.request)
        from_date, to_date = _resolve_range(form)
        context.update(
            {
                "page_title": "Salary Summary",
                "form": form,
                "from_date": from_date,
                "to_date": to_date,
                "data": ReportService.salary_summary(from_date, to_date),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            form = _valid_form(DateRangeForm, request)
            from_date, to_date = _resolve_range(form)
            data = ReportService.salary_summary(from_date, to_date)
            return ReportService.salary_summary_csv(data, from_date, to_date)
        return super().get(request, *args, **kwargs)


class AnalyticsView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "billing.view_invoice"
    template_name = "reports/analytics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _valid_form(DateRangeForm, self.request)
        from_date, to_date = _resolve_range(form)
        context.update(
            {
                "page_title": "Analytics",
                "form": form,
                "from_date": from_date,
                "to_date": to_date,
                "data": ReportService.analytics(from_date, to_date),
            }
        )
        return context
