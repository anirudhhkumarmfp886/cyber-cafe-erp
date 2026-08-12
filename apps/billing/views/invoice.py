"""
Billing views — thin CBVs delegating to the service layer.

The invoice list doubles as the counter billing screen (header form +
repeating line formset), mirroring the create-on-list pattern used by the
cash book and service catalog.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView

from apps.billing.forms.invoice import (
    CashOutForm,
    InvoiceForm,
    InvoiceLineFormSet,
    PaymentSplitFormSet,
    SettleInvoiceForm,
)
from apps.billing.models import Invoice, InvoiceStatus
from apps.billing.selectors.invoice_selector import InvoiceSelector
from apps.billing.services.billing_service import BillingService, CashOutService
from apps.customers.services.customer_service import CustomerService

_FORMSET_PREFIX = "line"
_PAY_PREFIX = "pay"


class InvoiceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "billing.view_invoice"
    template_name = "billing/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 20

    def get_queryset(self):
        filters = {
            "status": self.request.GET.get("status", ""),
            "from_date": self.request.GET.get("from_date", ""),
            "to_date": self.request.GET.get("to_date", ""),
            "q": self.request.GET.get("q", ""),
        }
        return InvoiceSelector.list_invoices(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Billing"
        context["statuses"] = InvoiceStatus.choices
        context["pending_total"] = InvoiceSelector.pending_total()
        context["can_create_customer"] = self.request.user.has_perm("customers.add_customer")
        if self.request.user.has_perm("billing.add_invoice"):
            context["invoice_form"] = InvoiceForm()
            context["line_formset"] = InvoiceLineFormSet(
                instance=Invoice(), prefix=_FORMSET_PREFIX
            )
            context["payment_formset"] = PaymentSplitFormSet(prefix=_PAY_PREFIX)
        return context

    def get_form_error_response(self, form, formset, payment_formset=None):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["invoice_form"] = form
        context["line_formset"] = formset
        context["payment_formset"] = payment_formset or PaymentSplitFormSet(prefix=_PAY_PREFIX)
        return self.render_to_response(context)

    def _line_custom_values(self, row_index: int) -> dict:
        """Collect the dynamic custom-field inputs for a formset row."""
        prefix = f"cf_{row_index}_"
        values = {}
        for key, value in self.request.POST.items():
            if key.startswith(prefix):
                values[key[len(prefix):]] = value
        return values

    def post(self, request):
        if not request.user.has_perm("billing.add_invoice"):
            return self.handle_no_permission()
        form = InvoiceForm(request.POST)
        formset = InvoiceLineFormSet(
            request.POST, instance=Invoice(), prefix=_FORMSET_PREFIX
        )
        pay_formset = PaymentSplitFormSet(request.POST, prefix=_PAY_PREFIX)
        pay_formset_valid = True
        if "pay-TOTAL_FORMS" in request.POST:
            pay_formset_valid = pay_formset.is_valid()
        if not (form.is_valid() and formset.is_valid() and pay_formset_valid):
            return self.get_form_error_response(form, formset, pay_formset)

        data = form.cleaned_data
        customer_name = (data.get("customer_name") or "").strip()
        if (
            customer_name
            and data.get("create_customer")
            and request.user.has_perm("customers.add_customer")
        ):
            try:
                data["customer"] = CustomerService.create_customer(
                    data={"full_name": customer_name}, by=request.user
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error("customer_name", str(exc))
                return self.get_form_error_response(form, formset, pay_formset)

        lines = []
        for line_form in formset.forms:
            if line_form.cleaned_data and not line_form.cleaned_data.get("DELETE", False):
                service = line_form.cleaned_data.get("service")
                qty = line_form.cleaned_data.get("qty")
                if service and qty:
                    row_index = line_form.prefix.split("-")[-1]
                    lines.append(
                        {
                            "service": service,
                            "qty": qty,
                            "custom": self._line_custom_values(row_index),
                        }
                    )

        payments = []
        for pay_form in pay_formset.forms:
            cleaned = pay_form.cleaned_data
            if cleaned and cleaned.get("amount"):
                payments.append(
                    {
                        "mode": cleaned["mode"],
                        "amount": cleaned["amount"],
                        "bank_account": cleaned.get("bank_account"),
                    }
                )
        try:
            invoice = BillingService.create_invoice(
                data=form.cleaned_data, lines=lines, payments=payments, by=request.user
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            form.add_error(None, str(exc))
            return self.get_form_error_response(form, formset, pay_formset)
        messages.success(request, f"Invoice {invoice.invoice_number} created ({invoice.total}).")
        return HttpResponseRedirect(reverse_lazy("billing:detail", kwargs={"pk": invoice.pk}))


class InvoiceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "billing.view_invoice"
    template_name = "billing/invoice_detail.html"
    context_object_name = "invoice"

    def get_object(self, queryset=None):
        return get_object_or_404(Invoice, id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.invoice_number
        context["lines"] = InvoiceSelector.lines(self.object)
        context["payments"] = InvoiceSelector.payments(self.object)
        if self.request.user.has_perm("billing.change_invoice"):
            context["settle_form"] = SettleInvoiceForm()
        return context


class InvoiceSettleView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "billing.change_invoice"
    http_method_names = ["post"]

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, id=pk)
        form = SettleInvoiceForm(request.POST)
        if form.is_valid():
            try:
                payment = BillingService.settle_invoice(
                    invoice=invoice,
                    amount=form.cleaned_data["amount"],
                    payment_mode=form.cleaned_data["payment_mode"],
                    notes=form.cleaned_data.get("notes", ""),
                    by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Payment of {payment.amount} recorded against {invoice.invoice_number}.",
                )
        else:
            messages.error(request, "Enter a valid amount and payment mode.")
        return HttpResponseRedirect(reverse_lazy("billing:detail", kwargs={"pk": invoice.pk}))


class InvoiceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "billing.delete_invoice"
    http_method_names = ["post"]

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, id=pk)
        BillingService.soft_delete_invoice(invoice=invoice, by=request.user)
        messages.success(request, f"{invoice.invoice_number} has been voided.")
        return HttpResponseRedirect(reverse_lazy("billing:list"))


class CashOutListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "billing.view_cashout"
    template_name = "billing/cashout_list.html"
    context_object_name = "cash_outs"
    paginate_by = 20

    def get_queryset(self):
        filters = {
            "from_date": self.request.GET.get("from_date", ""),
            "to_date": self.request.GET.get("to_date", ""),
        }
        return InvoiceSelector.list_cash_outs(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Cash Out / E-Sathi"
        if self.request.user.has_perm("billing.add_cashout"):
            context["cashout_form"] = CashOutForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["cashout_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("billing.add_cashout"):
            return self.handle_no_permission()
        form = CashOutForm(request.POST)
        if form.is_valid():
            try:
                cash_out = CashOutService.create_cash_out(data=form.cleaned_data, by=request.user)
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(
                request,
                f"{cash_out.reference_number}: cash given {cash_out.cash_given}, "
                f"commission {cash_out.commission_amount}.",
            )
            return HttpResponseRedirect(reverse_lazy("billing:cashout_list"))
        return self.get_form_error_response(form)
