"""
Service views — thin CBVs delegating to the service layer.

List page handles creation (like the cash book); the detail page shows the
append-only price history and handles edits, plus owner-only management of
service custom fields. The custom-fields JSON endpoint feeds the billing
screen's dynamic form rows.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView

from apps.services.forms.service import ServiceFilterForm, ServiceForm
from apps.services.forms.field import ServiceCustomFieldForm
from apps.services.models import CustomFieldType, Service, ServiceCustomField
from apps.services.selectors.service_selector import ServiceSelector
from apps.services.services.service_service import ServiceService


class ServiceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "services.view_service"
    template_name = "services/service_list.html"
    context_object_name = "services"
    paginate_by = 20

    def get_queryset(self):
        form = ServiceFilterForm(self.request.GET)
        filters = {}
        if form.is_valid():
            filters = {
                "category": form.cleaned_data.get("category"),
                "q": self.request.GET.get("q", ""),
            }
        return ServiceSelector.list_services(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Services"
        context["filter_form"] = ServiceFilterForm(self.request.GET)
        if self.request.user.has_perm("services.add_service"):
            context["service_form"] = ServiceForm()
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["service_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("services.add_service"):
            return self.handle_no_permission()
        form = ServiceForm(request.POST)
        if form.is_valid():
            try:
                service = ServiceService.create_service(data=form.cleaned_data, by=request.user)
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(request, f"Service {service.name} created.")
            return HttpResponseRedirect(reverse_lazy("services:detail", kwargs={"pk": service.pk}))
        return self.get_form_error_response(form)


class ServiceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "services.view_service"
    template_name = "services/service_detail.html"
    context_object_name = "service"

    def get_object(self, queryset=None):
        return get_object_or_404(Service.objects.select_related("category"), id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.name
        context["price_history"] = ServiceSelector.price_history(self.object)
        context["custom_fields"] = self.object.custom_fields.filter(is_active=True)
        context["field_types"] = CustomFieldType.choices
        if self.request.user.has_perm("services.change_service"):
            context["service_form"] = ServiceForm(instance=self.object)
        if self.request.user.has_perm("services.add_servicecustomfield"):
            context["custom_field_form"] = ServiceCustomFieldForm()
        return context

    def get_form_error_response(self, form):
        context = self.get_context_data(object=self.object)
        context["service_form"] = form
        return self.render_to_response(context)

    def post(self, request, pk):
        if not request.user.has_perm("services.change_service"):
            return self.handle_no_permission()
        self.object = self.get_object()
        form = ServiceForm(request.POST, instance=self.object)
        if form.is_valid():
            try:
                service = ServiceService.update_service(
                    self.object, data=form.cleaned_data, by=request.user
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(request, f"Service {service.name} updated.")
            return HttpResponseRedirect(reverse_lazy("services:detail", kwargs={"pk": service.pk}))
        return self.get_form_error_response(form)


class ServiceCustomFieldCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "services.add_servicecustomfield"
    http_method_names = ["post"]

    def post(self, request, pk):
        service = get_object_or_404(Service, id=pk)
        form = ServiceCustomFieldForm(request.POST)
        if form.is_valid():
            try:
                field = ServiceService.create_custom_field(
                    service=service, data=form.cleaned_data, by=request.user
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return HttpResponseRedirect(reverse_lazy("services:detail", kwargs={"pk": service.pk}))
            messages.success(request, f"Custom field '{field.label}' added.")
        else:
            messages.error(request, "Check the custom field form and try again.")
        return HttpResponseRedirect(reverse_lazy("services:detail", kwargs={"pk": service.pk}))


class ServiceCustomFieldDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "services.delete_servicecustomfield"
    http_method_names = ["post"]

    def post(self, request, pk, field_pk):
        service = get_object_or_404(Service, id=pk)
        field = get_object_or_404(ServiceCustomField, id=field_pk, service=service)
        ServiceService.delete_custom_field(field, by=request.user)
        messages.success(request, f"Custom field '{field.label}' removed.")
        return HttpResponseRedirect(reverse_lazy("services:detail", kwargs={"pk": service.pk}))


class ServiceCustomFieldsJsonView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Fields for the billing screen's dynamic form rows (role-filtered)."""

    permission_required = "services.view_service"

    def get(self, request):
        service = ServiceSelector.get_by_id(request.GET.get("service", ""))
        if service is None:
            return JsonResponse({"fields": []})
        return JsonResponse({"fields": ServiceSelector.custom_field_payload(service, request.user)})


class ServiceDeactivateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "services.delete_service"
    http_method_names = ["post"]

    def post(self, request, pk):
        service = get_object_or_404(Service, id=pk)
        ServiceService.deactivate_service(service, by=request.user)
        messages.success(request, f"{service.name} has been deactivated.")
        return HttpResponseRedirect(reverse_lazy("services:list"))
