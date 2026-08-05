"""Admin registrations for the billing app."""
from django.contrib import admin

from apps.billing.models import CashOut, Invoice, InvoiceLine, InvoicePayment
from apps.common.admin import BaseAdmin


@admin.register(Invoice)
class InvoiceAdmin(BaseAdmin):
    list_display = ("invoice_number", "customer", "payment_mode", "status", "total", "billed_on")
    list_filter = ("status", "payment_mode", "billed_on")
    search_fields = ("invoice_number", "customer__full_name")
    readonly_fields = BaseAdmin.readonly_fields + ("subtotal", "total", "cash_entry")
    autocomplete_fields = ("customer",)


@admin.register(InvoiceLine)
class InvoiceLineAdmin(BaseAdmin):
    list_display = ("invoice", "description", "qty", "unit_price", "amount")
    list_filter = ("invoice",)


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(BaseAdmin):
    list_display = ("invoice", "payment_date", "payment_mode", "amount")
    list_filter = ("payment_mode", "payment_date")
    search_fields = ("invoice__invoice_number",)


@admin.register(CashOut)
class CashOutAdmin(BaseAdmin):
    list_display = (
        "reference_number",
        "customer",
        "bank_account",
        "transfer_amount",
        "commission_percent",
        "commission_amount",
        "cash_given",
        "cash_out_on",
    )
    list_filter = ("cash_out_on",)
    search_fields = ("reference_number", "customer__full_name")
    readonly_fields = BaseAdmin.readonly_fields + (
        "transfer_amount",
        "commission_percent",
        "commission_amount",
        "cash_given",
    )
