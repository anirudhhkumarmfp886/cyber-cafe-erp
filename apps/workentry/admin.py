"""Admin registrations for the workentry app."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.workentry.models import WorkEntry


@admin.register(WorkEntry)
class WorkEntryAdmin(BaseAdmin):
    list_display = (
        "reference_number",
        "entry_date",
        "employee",
        "customer_display",
        "service",
        "status",
        "income",
        "total",
    )
    list_filter = ("status", "entry_date", "payment_mode")
    search_fields = ("reference_number", "customer__full_name", "customer_name")
    readonly_fields = BaseAdmin.readonly_fields + (
        "reference_number",
        "income",
        "total",
        "credit_used",
    )
    autocomplete_fields = ("customer", "service", "employee")
