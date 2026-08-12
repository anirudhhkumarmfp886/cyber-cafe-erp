"""
Work entry views — thin CBVs delegating to the service/selector layer.

* ``WorkEntryListView`` doubles as the counter screen: the header form on
  top creates a DRAFT, the table below lists drafts and saved entries.
* ``WorkEntryBillView`` shows the bill for one entry. While it is a DRAFT
  every field stays editable; "Save Bill" calls ``WorkEntryService.finalize``
  which books all ledgers atomically and locks the bill (SAVED).
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView

from apps.employees.models import Employee, Role
from apps.workentry.forms import WorkEntryForm
from apps.workentry.models import WorkEntry, WorkEntryStatus
from apps.workentry.selectors.workentry_selector import WorkEntrySelector
from apps.workentry.services.workentry_service import WorkEntryService


class WorkEntryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "workentry.view_workentry"
    template_name = "workentry/workentry_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        staff = self.request_staff
        is_manager = staff is not None and (
            staff.is_supervisor or staff.role == Role.ACCOUNTANT
        )
        filters = {
            "status": self.request.GET.get("status", ""),
            "from_date": self.request.GET.get("from_date", ""),
            "to_date": self.request.GET.get("to_date", ""),
            "q": self.request.GET.get("q", ""),
        }
        staff_filter = self.request.GET.get("staff", "")
        if is_manager and staff_filter:
            filters["staff"] = staff_filter
        return WorkEntrySelector.list_entries(filters, staff=staff, is_manager=is_manager)

    @property
    def request_staff(self):
        return getattr(self.request.user, "employee", None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.request_staff
        context["page_title"] = "Work Entry / Counter"
        context["statuses"] = WorkEntryStatus.choices
        context["is_manager"] = staff is not None and (
            staff.is_supervisor or staff.role == Role.ACCOUNTANT
        )
        if context["is_manager"]:
            context["staff_options"] = Employee.objects.filter(status="ACTIVE").order_by("full_name")
        context["totals"] = WorkEntrySelector.income_totals(self.object_list)
        if self.request.user.has_perm("workentry.add_workentry"):
            context["workentry_form"] = WorkEntryForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["workentry_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("workentry.add_workentry"):
            return self.handle_no_permission()
        form = WorkEntryForm(request.POST)
        if form.is_valid():
            try:
                entry = WorkEntryService.create_draft(data=form.cleaned_data, by=request.user)
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(
                request,
                f"Draft {entry.reference_number} created — open it to bill the customer.",
            )
            return HttpResponseRedirect(reverse_lazy("workentry:bill", kwargs={"pk": entry.pk}))
        return self.get_form_error_response(form)


class WorkEntryBillView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "workentry.view_workentry"
    template_editable = "workentry/workentry_bill_edit.html"
    template_saved = "workentry/workentry_bill.html"

    def _entry(self):
        return get_object_or_404(WorkEntry, id=self.kwargs["pk"])

    def _check_access(self, entry, staff):
        """Staff may open their own entries; supervisors/accountants all."""
        if staff is None:
            return
        if entry.employee_id != staff.pk and not (staff.is_supervisor or staff.role == Role.ACCOUNTANT):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("You can only open your own work entries.")

    def _editable(self, entry, staff):
        return (
            entry.status == WorkEntryStatus.DRAFT
            and self.request.user.has_perm("workentry.change_workentry")
            and (staff is None or entry.employee_id == staff.pk or staff.is_supervisor or staff.role == Role.ACCOUNTANT)
        )

    def get(self, request, pk):
        entry = self._entry()
        staff = getattr(request.user, "employee", None)
        self._check_access(entry, staff)
        context = {
            "page_title": f"Bill {entry.reference_number}",
            "entry": entry,
            "saved": entry.status == WorkEntryStatus.SAVED,
        }
        if self._editable(entry, staff):
            context["form"] = WorkEntryForm(instance=entry)
            return self._render(request, self.template_editable, context)
        return self._render(request, self.template_saved, context)

    def post(self, request, pk):
        entry = self._entry()
        staff = getattr(request.user, "employee", None)
        self._check_access(entry, staff)
        if entry.status == WorkEntryStatus.SAVED:
            messages.error(request, "This work entry is already saved.")
            return HttpResponseRedirect(reverse_lazy("workentry:bill", kwargs={"pk": entry.pk}))
        if not self._editable(entry, staff):
            return self.handle_no_permission()

        form = WorkEntryForm(request.POST, instance=entry)
        context = {"page_title": f"Bill {entry.reference_number}", "entry": entry, "saved": False}
        if form.is_valid():
            data = form.cleaned_data
            entry.entry_date = data["entry_date"]
            entry.customer = data.get("customer")
            entry.customer_name = (data.get("customer_name") or "").strip()
            entry.service = data["service"]
            entry.page_quantity = data.get("page_quantity") or 0
            entry.charged_amount = data["charged_amount"] or 0
            entry.payment_mode = data["payment_mode"]
            entry.credit_rest_mode = data.get("credit_rest_mode") or ""
            entry.bank_account = data.get("bank_account")
            entry.transfer_to_customer = data["transfer_to_customer"] or 0
            entry.transfer_on_behalf = data["transfer_on_behalf"] or 0
            entry.cash_withdrawal = data["cash_withdrawal"] or 0
            entry.notes = data.get("notes", "")
            entry.save()
            try:
                WorkEntryService.finalize(entry=entry, by=request.user)
            except ValueError as exc:
                messages.error(request, str(exc))
                context["form"] = form
                return self._render(request, self.template_editable, context)
            messages.success(
                request,
                f"Bill {entry.reference_number} saved — income {entry.income}, "
                f"total {entry.total}.",
            )
            return HttpResponseRedirect(reverse_lazy("workentry:bill", kwargs={"pk": entry.pk}))
        context["form"] = form
        return self._render(request, self.template_editable, context)

    def _render(self, request, template, context):
        from django.shortcuts import render

        return render(request, template, context)
