"""
Customer views — thin CBVs delegating to the service layer.

Create happens on the list page (like the cash book); detail/update and
soft-deactivate follow the employee pattern.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from apps.customers.forms.customer import CreditDepositForm, CustomerForm
from apps.customers.models import Customer
from apps.customers.selectors.customer_selector import CustomerSelector
from apps.customers.services.customer_service import CustomerService
from apps.employees.services.role_service import user_can_manage_customer_credit


class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "customers.view_customer"
    template_name = "customers/customer_list.html"
    context_object_name = "customers"
    paginate_by = 20

    def get_queryset(self):
        return CustomerSelector.list_customers(search=self.request.GET.get("q", "").strip())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Customers"
        context["q"] = self.request.GET.get("q", "")
        if self.request.user.has_perm("customers.add_customer"):
            context["customer_form"] = CustomerForm(user=self.request.user)
        return context

    def get_form_error_response(self, form):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        context["customer_form"] = form
        return self.render_to_response(context)

    def post(self, request):
        if not request.user.has_perm("customers.add_customer"):
            return self.handle_no_permission()
        form = CustomerForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                customer = CustomerService.create_customer(
                    data=form.cleaned_data, by=request.user
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                return self.get_form_error_response(form)
            messages.success(request, f"Customer {customer.full_name} added.")
            return HttpResponseRedirect(reverse_lazy("customers:detail", kwargs={"pk": customer.pk}))
        return self.get_form_error_response(form)


class CustomerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "customers.view_customer"
    template_name = "customers/customer_detail.html"
    context_object_name = "customer"

    def get_object(self, queryset=None):
        return get_object_or_404(Customer, id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object
        context["page_title"] = customer.full_name
        context["can_manage_credit"] = user_can_manage_customer_credit(self.request.user)
        context["financial_summary"] = CustomerSelector.get_financial_summary(customer)
        context["invoices"] = CustomerSelector.get_invoices(customer)
        context["prepaid_logs"] = CustomerSelector.get_prepaid_logs(customer)
        context["limit_logs"] = CustomerSelector.get_limit_logs(customer)
        if self.request.user.has_perm("customers.change_customer"):
            context["credit_form"] = CreditDepositForm()
        return context


class CustomerCreditDepositView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Deposit into / refund a customer's pre-paid credit balance and route to staff wallet."""
    permission_required = "customers.change_customer"
    http_method_names = ["post"]

    def post(self, request, pk):
        customer = get_object_or_404(Customer, id=pk)
        form = CreditDepositForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            if form.cleaned_data["direction"] == "REFUND":
                amount = -amount
            payment_mode = form.cleaned_data.get("payment_mode") or "CASH"
            payment_destination = form.cleaned_data.get("payment_destination") or "STAFF"
            description = form.cleaned_data.get("description", "")
            try:
                CustomerService.adjust_credit(
                    customer=customer,
                    amount=amount,
                    payment_mode=payment_mode,
                    payment_destination=payment_destination,
                    description=description,
                    by=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                customer.refresh_from_db()
                verb = "deposited" if amount > 0 else "refunded"
                messages.success(
                    request,
                    f"₹{abs(amount)} {verb} for {customer.full_name}. "
                    f"New credit balance: ₹{customer.credit_balance}.",
                )
        else:
            messages.error(request, "Enter a valid amount.")
        return HttpResponseRedirect(reverse_lazy("customers:detail", kwargs={"pk": customer.pk}))


class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "customers.change_customer"
    template_name = "customers/customer_form.html"
    form_class = CustomerForm
    model = Customer

    def get_object(self, queryset=None):
        return get_object_or_404(Customer, id=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit {self.object.full_name}"
        return context

    def form_valid(self, form):
        try:
            self.object = CustomerService.update_customer(
                self.get_object(), data=form.cleaned_data, by=self.request.user
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Customer updated successfully.")
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.object.pk})


class CustomerDeactivateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "customers.delete_customer"
    http_method_names = ["post"]

    def post(self, request, pk):
        customer = get_object_or_404(Customer, id=pk)
        CustomerService.deactivate_customer(customer, by=request.user)
        messages.success(request, f"{customer.full_name} has been deactivated.")
        return HttpResponseRedirect(reverse_lazy("customers:list"))
