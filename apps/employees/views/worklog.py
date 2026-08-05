"""
Work log views — thin CBVs delegating to the service layer.

The list page shows filters and (with permission) a create form; approve /
reject happen via a POST-only action view.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView

from apps.employees.forms.worklog import WorkLogEntryForm, WorkLogFilterForm
from apps.employees.models import WorkLogEntry
from apps.employees.selectors.worklog_selector import WorkLogSelector
from apps.employees.services.worklog_service import WorkLogService


class WorkLogListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "employees.view_worklogentry"
    template_name = "employees/worklog_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        form = WorkLogFilterForm(self.request.GET)
        filters = {}
        if form.is_valid():
            filters = {
                "employee": form.cleaned_data.get("employee"),
                "status": form.cleaned_data.get("status"),
                "from_date": form.cleaned_data.get("from_date"),
                "to_date": form.cleaned_data.get("to_date"),
                "q": self.request.GET.get("q", ""),
            }
        return WorkLogSelector.list_entries(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Daily Work Log"
        context["filter_form"] = WorkLogFilterForm(self.request.GET)
        context["pending_count"] = WorkLogSelector.pending_count()
        if self.request.user.has_perm("employees.add_worklogentry"):
            context["entry_form"] = WorkLogEntryForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["entry_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("employees.add_worklogentry"):
            return self.handle_no_permission()
        form = WorkLogEntryForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                entry = WorkLogService.create_entry(
                    employee=data["employee"],
                    work_date=data["work_date"],
                    hours_worked=data.get("hours_worked"),
                    start_time=data.get("start_time"),
                    end_time=data.get("end_time"),
                    notes=data.get("notes", ""),
                    by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(request, f"Logged {entry.hours_worked}h for {entry.employee.full_name}.")
            return HttpResponseRedirect(reverse_lazy("employees:worklog_list"))
        return self.get_form_error_response(form)


class WorkLogActionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_worklogentry"
    http_method_names = ["post"]

    def post(self, request, pk, action):
        entry = get_object_or_404(WorkLogEntry, id=pk)
        if action not in ("approve", "reject"):
            messages.error(request, "Unknown action.")
            return HttpResponseRedirect(reverse_lazy("employees:worklog_list"))
        try:
            if action == "approve":
                WorkLogService.approve_entry(entry, by=request.user)
                messages.success(
                    request,
                    f"Approved {entry.employee.full_name}'s log — salary credited.",
                )
            else:
                WorkLogService.reject_entry(entry, by=request.user)
                messages.warning(request, f"Rejected {entry.employee.full_name}'s log.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return HttpResponseRedirect(reverse_lazy("employees:worklog_list"))
