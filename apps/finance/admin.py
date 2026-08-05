"""Admin configuration for finance models."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.finance.models import BankAccount, BankTransaction, CashBookEntry


@admin.register(CashBookEntry)
class CashBookEntryAdmin(BaseAdmin):
    list_display = ("reference_number", "entry_date", "entry_type", "category", "amount", "payment_mode", "created_by")
    list_filter = ("entry_type", "category", "payment_mode", "entry_date")
    search_fields = ("reference_number", "party_name", "description")


@admin.register(BankAccount)
class BankAccountAdmin(BaseAdmin):
    list_display = ("account_name", "bank_name", "account_number", "account_type", "is_active")
    search_fields = ("account_name", "bank_name", "account_number", "ifsc_code")


@admin.register(BankTransaction)
class BankTransactionAdmin(BaseAdmin):
    list_display = ("reference_number", "account", "entry_date", "transaction_type", "category", "amount")
    list_filter = ("transaction_type", "category", "entry_date")
    search_fields = ("reference_number", "party_name", "description", "account__account_name")
    autocomplete_fields = ("account",)
