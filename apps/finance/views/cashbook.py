"""Cash book views."""
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
from apps.finance.forms.cashbook import CashBookEntryForm, CashBookFilterForm, OwnerCashForm
from apps.finance.models import CashBookEntry
from apps.finance.models.enums import BankTransactionCategory
from apps.finance.selectors.cashbook_selector import CashBookSelector
from apps.finance.services.bank_service import BankService
from apps.finance.services.cashbook_service import CashBookService



class CashBookListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "finance.view_cashbookentry"
    template_name = "finance/cashbook_list.html"
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
        as_on_balance = CashBookSelector.balance_on(as_on_date, staff=staff)
        context["as_on_balance"] = as_on_balance

        from apps.employees.selectors.wallet_selector import WalletSelector
        from apps.employees.models import WalletType

        if staff is None:
            staff_cash_float_breakdown = WalletSelector.staff_float_breakdown(WalletType.CASH, on_date=as_on_date)
            total_staff_cash_float = WalletSelector.total_staff_float(WalletType.CASH, on_date=as_on_date)
            drawer_balance = CashBookSelector.drawer_balance_on(as_on_date)
            entire_shop_cash_float = drawer_balance + total_staff_cash_float
            staff_cash_float = 0
            staff_online_float = 0
        else:
            staff_cash_float_breakdown = []
            total_staff_cash_float = 0
            drawer_balance = as_on_balance
            entire_shop_cash_float = as_on_balance
            from apps.employees.services.wallet_service import WalletService
            staff_cash_wallet = WalletService.get_or_create_wallet(staff, WalletType.CASH)
            staff_online_wallet = WalletService.get_or_create_wallet(staff, WalletType.ONLINE)
            staff_cash_float = WalletService.balance_of_on(staff_cash_wallet, as_on_date)
            staff_online_float = WalletService.balance_of_on(staff_online_wallet, as_on_date)
            context["staff_cash_wallet"] = staff_cash_wallet
            context["staff_online_wallet"] = staff_online_wallet

        context["drawer_balance"] = drawer_balance
        context["staff_cash_float_breakdown"] = staff_cash_float_breakdown
        context["total_staff_cash_float"] = total_staff_cash_float
        context["entire_shop_cash_float"] = entire_shop_cash_float
        context["staff_cash_float"] = staff_cash_float
        context["staff_online_float"] = staff_online_float

        emp = getattr(request.user, "employee", None)
        can_add_income = (
            request.user.is_superuser
            or request.user.has_perm("finance.add_cashbookincome")
            or bool(emp and (emp.can_create_bills or emp.can_manage_topup or emp.can_record_expenses))
        )
        can_add_expense = (
            request.user.is_superuser
            or request.user.has_perm("finance.add_cashbookexpense")
            or bool(emp and emp.can_record_expenses)
        )
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
        emp = getattr(request.user, "employee", None)
        can_add_income = (
            request.user.is_superuser
            or request.user.has_perm("finance.add_cashbookincome")
            or bool(emp and (emp.can_create_bills or emp.can_manage_topup or emp.can_record_expenses))
        )
        can_add_expense = (
            request.user.is_superuser
            or request.user.has_perm("finance.add_cashbookexpense")
            or bool(emp and emp.can_record_expenses)
        )
        allowed_types = []
        if can_add_income:
            allowed_types.append("INCOME")
        if can_add_expense:
            allowed_types.append("EXPENSE")
        if not allowed_types:
            return self.handle_no_permission()
        form = CashBookEntryForm(request.POST, allowed_entry_types=tuple(allowed_types))
        if form.is_valid():
            data = form.cleaned_data
            amount = data["amount"]
            entry_type = data["entry_type"]
            payment_mode = data["payment_mode"]
            category = data["category"]
            party_name = data.get("party_name", "")
            description = data.get("description", "").strip()
            entry_date = data.get("entry_date")
            bank_account = data.get("bank_account")

            paid_from = data.get("paid_from") or "SHOP_DRAWER"
            try:
                if entry_type == "INCOME":
                    if payment_mode in ["UPI", "CARD", "BANK_TRANSFER"] and bank_account:
                        with transaction.atomic():
                            bank_txn = BankService.deposit(
                                account=bank_account,
                                amount=amount,
                                category=BankTransactionCategory.PAYMENT_RECEIVED,
                                party_name=party_name,
                                description=f"UPI Income ({category}): {description}".strip(),
                                entry_date=entry_date,
                                by=request.user,
                            )
                            entry_desc = f"{description} [Received in {bank_account.account_name} ({bank_account.bank_name}) - Ref: {bank_txn.reference_number}]".strip()
                            entry = CashBookService.record_income(
                                amount=amount,
                                category=category,
                                payment_mode=payment_mode,
                                party_name=party_name,
                                description=entry_desc,
                                entry_date=entry_date,
                                by=request.user,
                            )
                            bank_txn.related_reference = entry.reference_number
                            bank_txn.save(update_fields=["related_reference", "updated_at"])
                            messages.success(
                                request,
                                f"Recorded UPI income {entry.reference_number} & credited ₹{amount} to {bank_account.bank_name} (Ref: {bank_txn.reference_number}).",
                            )
                    else:
                        entry = CashBookService.record_income(
                            amount=amount,
                            category=category,
                            payment_mode="CASH",
                            party_name=party_name,
                            description=description,
                            entry_date=entry_date,
                            by=request.user,
                        )
                        messages.success(request, f"Recorded income {entry.reference_number} in Cash Book.")
                else:
                    # EXPENSE
                    if payment_mode in ["UPI", "CARD", "BANK_TRANSFER"] and bank_account:
                        with transaction.atomic():
                            bank_txn = BankService.withdraw(
                                account=bank_account,
                                amount=amount,
                                category=BankTransactionCategory.EXPENSE_PAYMENT,
                                party_name=party_name,
                                description=f"UPI Expense ({category}): {description}".strip(),
                                entry_date=entry_date,
                                by=request.user,
                            )
                            entry_desc = f"{description} [Paid via {bank_account.account_name} ({bank_account.bank_name}) - Ref: {bank_txn.reference_number}]".strip()
                            entry = CashBookService.record_expense(
                                amount=amount,
                                category=category,
                                payment_mode=payment_mode,
                                party_name=party_name,
                                description=entry_desc,
                                entry_date=entry_date,
                                by=request.user,
                            )
                            bank_txn.related_reference = entry.reference_number
                            bank_txn.save(update_fields=["related_reference", "updated_at"])
                            messages.success(
                                request,
                                f"Recorded UPI expense {entry.reference_number} & debited ₹{amount} from {bank_account.account_name} (Ref: {bank_txn.reference_number}).",
                            )
                    elif paid_from == "STAFF_FLOAT" and emp:
                        from apps.employees.services.wallet_service import WalletService
                        from apps.employees.models import WalletType, WalletTransactionCategory
                        cash_wallet = WalletService.get_or_create_wallet(emp, WalletType.CASH)
                        txn = WalletService.debit(
                            wallet=cash_wallet,
                            amount=amount,
                            category=WalletTransactionCategory.EXPENSE,
                            description=f"Counter float cash expense ({category}): {description}".strip(),
                            source=emp.full_name,
                            destination=party_name or "Shop Expense",
                            by=request.user,
                            entry_date=entry_date,
                        )
                        messages.success(
                            request,
                            f"Recorded expense {txn.reference_number} debited from your Counter Float (₹{amount}).",
                        )
                    else:
                        # Paid directly from Shop Drawer (Main Galla)
                        entry = CashBookService.record_expense(
                            amount=amount,
                            category=category,
                            payment_mode="CASH",
                            party_name=party_name,
                            description=description,
                            entry_date=entry_date,
                            by=request.user,
                        )
                        messages.success(request, f"Recorded expense {entry.reference_number} in Shop Cash Drawer.")
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
            amount = data["amount"]
            action = data["action"]
            source = data.get("source", "DIRECT")
            bank_account = data.get("bank_account")
            desc = data.get("description", "").strip()

            try:
                if source == "BANK" and bank_account:
                    with transaction.atomic():
                        if action == "DEPOSIT":
                            # Bank withdrawal -> Cash Drawer deposit
                            bank_txn = BankService.withdraw(
                                account=bank_account,
                                amount=amount,
                                category=BankTransactionCategory.WITHDRAWAL,
                                party_name="Shop Cash Drawer",
                                description=f"Cash withdrawal for Shop Drawer. {desc}".strip(),
                                by=request.user,
                            )
                            cb_entry = CashBookService.owner_deposit(
                                amount=amount,
                                payment_mode="CASH",
                                description=f"Transferred from {bank_account.account_name} ({bank_account.bank_name} - {bank_account.account_number}) [Ref: {bank_txn.reference_number}]. {desc}".strip(),
                                by=request.user,
                            )
                            bank_txn.related_reference = cb_entry.reference_number
                            bank_txn.save(update_fields=["related_reference", "updated_at"])
                            messages.success(
                                request,
                                f"Successfully transferred ₹{amount} from {bank_account.account_name} to Shop Cash Drawer ({cb_entry.reference_number}).",
                            )
                        else:
                            # Cash Drawer withdrawal -> Bank deposit
                            cb_entry = CashBookService.owner_withdraw(
                                amount=amount,
                                payment_mode="CASH",
                                description=f"Deposited into {bank_account.account_name} ({bank_account.bank_name} - {bank_account.account_number}). {desc}".strip(),
                                by=request.user,
                            )
                            bank_txn = BankService.deposit(
                                account=bank_account,
                                amount=amount,
                                category=BankTransactionCategory.DEPOSIT,
                                party_name="Shop Cash Drawer",
                                description=f"Cash deposit from Shop Drawer [Ref: {cb_entry.reference_number}]. {desc}".strip(),
                                by=request.user,
                            )
                            bank_txn.related_reference = cb_entry.reference_number
                            bank_txn.save(update_fields=["related_reference", "updated_at"])
                            messages.success(
                                request,
                                f"Successfully deposited ₹{amount} from Shop Cash Drawer into {bank_account.bank_name} ({bank_txn.reference_number}).",
                            )
                else:
                    # Direct Cash (Pocket / Personal)
                    if action == "WITHDRAW":
                        entry = CashBookService.owner_withdraw(
                            amount=amount,
                            payment_mode=data["payment_mode"],
                            description=desc,
                            by=request.user,
                        )
                        messages.success(request, f"Withdrew ₹{entry.amount} from Shop Cash Drawer ({entry.reference_number}).")
                    else:
                        entry = CashBookService.owner_deposit(
                            amount=amount,
                            payment_mode=data["payment_mode"],
                            description=desc,
                            by=request.user,
                        )
                        messages.success(request, f"Deposited ₹{entry.amount} into Shop Cash Drawer ({entry.reference_number}).")
            except ValueError as exc:
                messages.error(request, str(exc))
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}" if field != "__all__" else error)
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))



class CashBookDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.delete_cashbookentry"
    http_method_names = ["post"]

    def post(self, request, pk):
        entry = get_object_or_404(CashBookEntry, id=pk)
        CashBookService.soft_delete_entry(entry, by=request.user)
        messages.success(request, f"Entry {entry.reference_number} deleted (soft).")
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))


class CashBookBulkDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "finance.delete_cashbookentry"
    http_method_names = ["post"]

    def post(self, request):
        entry_ids = request.POST.getlist("selected_entries")
        if not entry_ids:
            messages.warning(request, "Koi bhi entry select nahi ki gayi thi.")
            return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))

        count = 0
        with transaction.atomic():
            for entry_id in entry_ids:
                entry = CashBookEntry.objects.filter(id=entry_id, is_active=True).first()
                if entry:
                    CashBookService.soft_delete_entry(entry, by=request.user)
                    count += 1

        messages.success(request, f"{count} entry(s) successfully deleted.")
        return HttpResponseRedirect(reverse_lazy("finance:cashbook_list"))
