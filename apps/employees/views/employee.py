"""
Employee views — thin CBVs that delegate all business logic to the service
layer. No database writes or business decisions happen here.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.employees.forms.employee import EmployeeCreateForm, EmployeeUpdateForm
from apps.employees.models import Employee, Role
from apps.employees.selectors.employee_selector import EmployeeSelector
from apps.employees.services.employee_service import EmployeeService
from apps.employees.services.role_service import user_can_manage_permissions, user_can_view_all_profiles


class EmployeeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "employees.view_employee"
    template_name = "employees/employee_list.html"
    context_object_name = "employees"
    paginate_by = 20

    def get_queryset(self):
        queryset = EmployeeSelector.list_active()
        search = self.request.GET.get("q", "").strip()
        role = self.request.GET.get("role", "").strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(employee_code__icontains=search)
                | Q(user__username__icontains=search)
            )
        if role and role in Role.values:
            queryset = queryset.filter(role=role)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Employees"
        context["roles"] = Role.choices
        context["q"] = self.request.GET.get("q", "")
        context["selected_role"] = self.request.GET.get("role", "")
        context["can_view_all_profiles"] = user_can_view_all_profiles(self.request.user)
        context["can_manage_permissions"] = user_can_manage_permissions(self.request.user)
        return context


class EmployeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "employees.add_employee"
    template_name = "employees/employee_form.html"
    form_class = EmployeeCreateForm
    model = Employee

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Employee"
        context["can_manage_permissions"] = user_can_manage_permissions(self.request.user)
        return context

    def form_valid(self, form):
        try:
            self.object = EmployeeService.create_employee(
                data=form.cleaned_data, by=self.request.user
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f"Employee {self.object.full_name} created successfully.")
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("employees:detail", kwargs={"pk": self.object.pk})


class EmployeeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_object(self, queryset=None):
        return get_object_or_404(Employee, id=self.kwargs["pk"])

    def has_permission(self):
        obj = self.get_object()
        return user_can_view_all_profiles(self.request.user) or (obj.user and obj.user == self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        context["page_title"] = employee.full_name
        context["can_view_all_profiles"] = user_can_view_all_profiles(self.request.user)
        context["can_manage_permissions"] = user_can_manage_permissions(self.request.user)
        context["is_own_profile"] = (employee.user == self.request.user)
        context["income_stats"] = EmployeeSelector.get_income_stats(employee)
        
        try:
            from apps.employees.models import WalletType
            from apps.employees.services.wallet_service import WalletService
            cash_wallet = WalletService.get_or_create_wallet(employee, WalletType.CASH)
            online_wallet = WalletService.get_or_create_wallet(employee, WalletType.ONLINE)
            cash_bal = WalletService.balance_of(cash_wallet)
            online_bal = WalletService.balance_of(online_wallet)
            context["cash_wallet"] = cash_wallet
            context["cash_balance"] = cash_bal
            context["online_wallet"] = online_wallet
            context["online_balance"] = online_bal
            context["total_wallet_balance"] = cash_bal + online_bal
        except Exception:
            pass
        return context


class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "employees.change_employee"
    template_name = "employees/employee_form.html"
    form_class = EmployeeUpdateForm
    model = Employee

    def get_object(self, queryset=None):
        return get_object_or_404(Employee, id=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit {self.object.full_name}"
        context["can_manage_permissions"] = user_can_manage_permissions(self.request.user)
        return context

    def form_valid(self, form):
        self.object = EmployeeService.update_employee(
            self.get_object(), data=form.cleaned_data, by=self.request.user
        )
        messages.success(self.request, "Employee updated successfully.")
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("employees:detail", kwargs={"pk": self.object.pk})


class EmployeeDeactivateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.delete_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.deactivate_employee(employee, by=request.user)
        messages.success(request, f"{employee.full_name} has been deactivated.")
        return HttpResponseRedirect(reverse_lazy("employees:list"))


class EmployeeToggleBillingView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        if not user_can_manage_permissions(request.user):
            return self.handle_no_permission()
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.toggle_billing_access(employee, by=request.user)
        action_str = "granted to" if employee.can_create_bills else "revoked from"
        messages.success(request, f"Billing creation permission has been {action_str} {employee.full_name}.")
        return HttpResponseRedirect(reverse_lazy("employees:detail", kwargs={"pk": employee.pk}))


class EmployeeToggleTopupView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        if not user_can_manage_permissions(request.user):
            return self.handle_no_permission()
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.toggle_topup_access(employee, by=request.user)
        action_str = "granted to" if employee.can_manage_topup else "revoked from"
        messages.success(request, f"Top-up & Owner Cash permission has been {action_str} {employee.full_name}.")
        return HttpResponseRedirect(reverse_lazy("employees:detail", kwargs={"pk": employee.pk}))


class EmployeeTogglePersonalUpiView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        if not user_can_manage_permissions(request.user):
            return self.handle_no_permission()
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.toggle_personal_upi_access(employee, by=request.user)
        action_str = "granted to" if employee.can_collect_personal_upi else "revoked from"
        messages.success(
            request,
            f"Personal UPI & Flexible Payment Collection access has been {action_str} {employee.full_name}.",
        )
        return HttpResponseRedirect(reverse_lazy("employees:detail", kwargs={"pk": employee.pk}))


class EmployeeToggleShopFinanceView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        if not user_can_manage_permissions(request.user):
            return self.handle_no_permission()
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.toggle_shop_finance_access(employee, by=request.user)
        action_str = "granted to" if employee.can_view_shop_finance else "revoked from"
        messages.success(
            request,
            f"Entire Shop Main Galla & UPI Book view access has been {action_str} {employee.full_name}.",
        )
        return HttpResponseRedirect(reverse_lazy("employees:detail", kwargs={"pk": employee.pk}))


class EmployeeToggleManagePermissionsView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        if not user_can_manage_permissions(request.user):
            return self.handle_no_permission()
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.toggle_manage_permissions_access(employee, by=request.user)
        action_str = "granted to" if employee.can_manage_permissions else "revoked from"
        messages.success(
            request,
            f"Permission management access has been {action_str} {employee.full_name}.",
        )
        return HttpResponseRedirect(reverse_lazy("employees:detail", kwargs={"pk": employee.pk}))


class EmployeeToggleCustomerCreditView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "employees.change_employee"
    http_method_names = ["post"]

    def post(self, request, pk):
        if not user_can_manage_permissions(request.user):
            return self.handle_no_permission()
        employee = get_object_or_404(Employee, id=pk)
        EmployeeService.toggle_customer_credit_access(employee, by=request.user)
        action_str = "granted to" if employee.can_manage_customer_credit else "revoked from"
        messages.success(
            request,
            f"Customer Credit Management access has been {action_str} {employee.full_name}.",
        )
        return HttpResponseRedirect(reverse_lazy("employees:detail", kwargs={"pk": employee.pk}))



