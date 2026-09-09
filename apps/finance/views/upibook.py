"""Shop UPI Book views."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView

from apps.employees.models import Employee, EmploymentStatus
from apps.finance.forms.upibook import (
    OwnerUPIFloatForm,
    UPIBookEntryForm,
    UPIBookFilterForm,
)
from apps.finance.models import BankAccount, UPIBookEntry
from apps.finance.models.enums import CashEntryType
from apps.finance.selectors.upibook_selector import UPIBookSelector
from apps.finance.services.upibook_service import UPIBookService


class UPIBookListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = "finance/upibook_list.html"
    context_object_name = "entries"
    paginate_by = 25

    def can_view_shop(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.has_perm("finance.withdraw_shop_cash"):
            return True
        emp = getattr(user, "employee", None)
        if emp and (emp.is_supervisor or emp.can_manage_topup or getattr(emp, "can_view_shop_finance", False)):
            return True
        return False

    def has_permission(self):
        return self.can_view_shop() or bool(getattr(self.request.user, "employee", None))

    def effective_staff(self):
        """Non-privileged staff always see only their own UPI transactions."""
        if self.can_view_shop():
            staff_id = self.request.GET.get("staff")
            if staff_id:
                return get_object_or_404(Employee, id=staff_id)
            return None
        return getattr(self.request.user, "employee", None)

    def get_selected_account(self):
        acc_id = self.request.GET.get("bank_account")
        if acc_id:
            return BankAccount.objects.filter(id=acc_id, is_active=True).first()
        return None

    def get_queryset(self):
        form = UPIBookFilterForm(self.request.GET)
        filters = {"staff": self.effective_staff()}
        if form.is_valid():
            filters.update(
                {
                    "bank_account": form.cleaned_data.get("bank_account"),
                    "entry_type": form.cleaned_data.get("entry_type"),
                    "category": form.cleaned_data.get("category"),
                    "from_date": form.cleaned_data.get("from_date"),
                    "to_date": form.cleaned_data.get("to_date"),
                    "q": self.request.GET.get("q", ""),
                }
            )
        return UPIBookSelector.list_entries(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.get_selected_account()
        staff = self.effective_staff()
        today = date.today()
        as_on = self.request.GET.get("as_on")
        try:
            as_on_date = date.fromisoformat(as_on) if as_on else today
        except ValueError:
            as_on_date = today

        pool_balance = UPIBookSelector.balance_on(as_on_date, staff=staff, bank_account=account)
        from apps.employees.selectors.wallet_selector import WalletSelector
        from apps.employees.models import WalletType

        if staff is None:
            staff_float_breakdown = WalletSelector.staff_float_breakdown(WalletType.ONLINE, on_date=as_on_date)
            total_staff_float = WalletSelector.total_staff_float(WalletType.ONLINE, on_date=as_on_date)
            entire_shop_upi_float = pool_balance + total_staff_float
            staff_online_float = 0
            staff_cash_float = 0
        else:
            staff_float_breakdown = []
            total_staff_float = 0
            entire_shop_upi_float = pool_balance
            from apps.employees.services.wallet_service import WalletService
            staff_online_wallet = WalletService.get_or_create_wallet(staff, WalletType.ONLINE)
            staff_cash_wallet = WalletService.get_or_create_wallet(staff, WalletType.CASH)
            staff_online_float = WalletService.balance_of_on(staff_online_wallet, as_on_date)
            staff_cash_float = WalletService.balance_of_on(staff_cash_wallet, as_on_date)
            context["staff_online_wallet"] = staff_online_wallet
            context["staff_cash_wallet"] = staff_cash_wallet

        context["page_title"] = "Shop UPI Book"
        context["filter_form"] = UPIBookFilterForm(self.request.GET)
        context["staff"] = staff
        context["staff_label"] = staff.get_full_name() if staff else "Entire Shop (Main Digital Pool)"
        context["can_view_shop"] = self.can_view_shop()
        context["staff_list"] = (
            Employee.objects.filter(status=EmploymentStatus.ACTIVE).order_by("full_name")
            if self.can_view_shop()
            else []
        )
        context["selected_account"] = account
        context["as_on"] = as_on_date
        context["balance"] = pool_balance
        context["staff_float_breakdown"] = staff_float_breakdown
        context["total_staff_float"] = total_staff_float
        context["entire_shop_upi_float"] = entire_shop_upi_float
        context["staff_online_float"] = staff_online_float
        context["staff_cash_float"] = staff_cash_float
        context["today_inflow"] = UPIBookSelector.today_inflow(day=as_on_date, staff=staff, bank_account=account)
        context["today_outflow"] = UPIBookSelector.today_outflow(day=as_on_date, staff=staff, bank_account=account)
        context["today_net"] = context["today_inflow"] - context["today_outflow"]

        can_manage = self.request.user.is_superuser or self.request.user.has_perm("finance.add_bankaccount")
        context["can_manage"] = can_manage
        context["entry_form"] = UPIBookEntryForm() if can_manage else None
        context["owner_float_form"] = OwnerUPIFloatForm() if can_manage else None

        return context

    def post(self, request):
        if not (request.user.is_superuser or request.user.has_perm("finance.add_bankaccount")):
            return self.handle_no_permission()

        form = UPIBookEntryForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            entry_type = data["entry_type"]
            category = data["category"]
            amount = data["amount"]
            bank_account = data.get("bank_account")
            party_name = data.get("party_name", "").strip()
            desc = data.get("description", "").strip()
            entry_date = data.get("entry_date") or date.today()

            try:
                if entry_type == CashEntryType.INCOME:
                    entry = UPIBookService.record_income(
                        amount=amount,
                        category=category,
                        bank_account=bank_account,
                        party_name=party_name or "Shop UPI Customer",
                        description=desc,
                        entry_date=entry_date,
                        by=request.user,
                    )
                    messages.success(
                        request,
                        f"Recorded UPI Inflow {entry.reference_number}: ₹{amount} added to Shop UPI Book.",
                    )
                else:
                    entry = UPIBookService.record_expense(
                        amount=amount,
                        category=category,
                        bank_account=bank_account,
                        party_name=party_name or "Shop UPI Vendor/Expense",
                        description=desc,
                        entry_date=entry_date,
                        by=request.user,
                    )
                    messages.success(
                        request,
                        f"Recorded UPI Outflow {entry.reference_number}: ₹{amount} debited from Shop UPI Book.",
                    )
            except ValueError as exc:
                messages.error(request, str(exc))
                form.add_error(None, str(exc))
                self.object_list = self.get_queryset()
                context = self.get_context_data()
                context["entry_form"] = form
                return self.render_to_response(context)
        else:
            self.object_list = self.get_queryset()
            context = self.get_context_data()
            context["entry_form"] = form
            return self.render_to_response(context)

        return HttpResponseRedirect(reverse_lazy("finance:upibook_list"))


class OwnerUPIActionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    http_method_names = ["post"]

    def has_permission(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.has_perm("finance.add_bankaccount"):
            return True
        emp = getattr(user, "employee", None)
        if emp and (emp.is_supervisor or emp.can_manage_topup or getattr(emp, "can_view_shop_finance", False)):
            return True
        return False

    def post(self, request):
        form = OwnerUPIFloatForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            action = data["action"]
            amount = data["amount"]
            bank_account = data.get("bank_account")
            staff = data.get("staff")
            desc = data.get("description", "").strip()

            try:
                if action == OwnerUPIFloatForm.Action.LOAD_FROM_BANK:
                    upi_entry, bank_txn = UPIBookService.fund_from_bank(
                        bank_account=bank_account,
                        amount=amount,
                        description=desc,
                        by=request.user,
                    )
                    messages.success(
                        request,
                        f"Successfully transferred float ₹{amount:.2f} from {bank_account.account_name} to Shop UPI Book ({upi_entry.reference_number}).",
                    )
                elif action == OwnerUPIFloatForm.Action.SWEEP_TO_BANK:
                    upi_entry, bank_txn = UPIBookService.sweep_to_bank(
                        bank_account=bank_account,
                        amount=amount,
                        description=desc,
                        by=request.user,
                    )
                    messages.success(
                        request,
                        f"Successfully swept ₹{amount:.2f} from Shop UPI Book into {bank_account.account_name} ({bank_txn.reference_number}).",
                    )
                elif action == OwnerUPIFloatForm.Action.REIMBURSE_CASH:
                    upi_entry, target_txn = UPIBookService.reimburse_cash_float(
                        amount=amount,
                        staff=staff,
                        description=desc,
                        by=request.user,
                    )
                    dest_label = staff.full_name if staff else "Shop Cash Drawer"
                    messages.success(
                        request,
                        f"Successfully reimbursed ₹{amount:.2f} cash float to {dest_label} from Shop UPI Book ({upi_entry.reference_number}).",
                    )
            except ValueError as exc:
                messages.error(request, str(exc))
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(
                        request,
                        f"{field.replace('_', ' ').title()}: {error}" if field != "__all__" else error,
                    )

        return HttpResponseRedirect(reverse_lazy("finance:upibook_list"))


class UPIBookDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.delete_upibookentry"
    http_method_names = ["post"]

    def post(self, request, pk):
        entry = get_object_or_404(UPIBookEntry, id=pk)
        UPIBookService.soft_delete_entry(entry, by=request.user)
        messages.success(request, f"UPI entry {entry.reference_number} deleted successfully.")
        return HttpResponseRedirect(reverse_lazy("finance:upibook_list"))


class UPIBookBulkDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.delete_upibookentry"
    http_method_names = ["post"]

    def post(self, request):
        entry_ids = request.POST.getlist("selected_entries")
        if not entry_ids:
            messages.warning(request, "Koi bhi entry select nahi ki gayi thi.")
            return HttpResponseRedirect(reverse_lazy("finance:upibook_list"))

        count = 0
        with transaction.atomic():
            for entry_id in entry_ids:
                entry = UPIBookEntry.objects.filter(id=entry_id, is_active=True).first()
                if entry:
                    UPIBookService.soft_delete_entry(entry, by=request.user)
                    count += 1

        messages.success(request, f"{count} UPI entry(s) successfully deleted.")
        return HttpResponseRedirect(reverse_lazy("finance:upibook_list"))

