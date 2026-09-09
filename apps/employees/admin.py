"""Admin configuration for employees."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.employees.models import Employee, Wallet, WalletTransaction, WorkLogEntry


@admin.register(Employee)
class EmployeeAdmin(BaseAdmin):
    list_display = ("employee_code", "full_name", "role", "status", "is_active", "created_at")
    list_filter = ("role", "status", "is_active")
    search_fields = ("employee_code", "full_name", "user__username", "personal_phone")
    autocomplete_fields = ("user",)
    list_select_related = ("user",)


@admin.register(Wallet)
class WalletAdmin(BaseAdmin):
    list_display = ("employee", "wallet_type", "employee_code", "current_balance", "is_active", "created_at")
    list_filter = ("wallet_type", "is_active")
    list_select_related = ("employee",)
    search_fields = ("employee__employee_code", "employee__full_name")

    @admin.display(description="Employee code")
    def employee_code(self, obj):
        return obj.employee.employee_code

    @admin.display(description="Current Balance (₹)")
    def current_balance(self, obj):
        return f"₹{obj.balance:,.2f}"


@admin.register(WalletTransaction)
class WalletTransactionAdmin(BaseAdmin):
    list_display = ("reference_number", "wallet", "entry_date", "transaction_type", "category", "amount", "balance_after", "created_by")
    list_filter = ("transaction_type", "category", "wallet__wallet_type", "entry_date")
    search_fields = ("reference_number", "description", "related_reference", "wallet__employee__full_name")
    autocomplete_fields = ("wallet",)


@admin.register(WorkLogEntry)
class WorkLogEntryAdmin(BaseAdmin):
    list_display = ("employee", "work_date", "hours_worked", "rate_applied", "status", "approved_at")
    list_filter = ("status", "work_date")
    search_fields = ("employee__full_name", "employee__employee_code", "notes")
    autocomplete_fields = ("employee",)
    list_select_related = ("employee",)
