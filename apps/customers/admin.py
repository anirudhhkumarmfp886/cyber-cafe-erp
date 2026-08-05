"""Admin configuration for customers."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(BaseAdmin):
    list_display = ("full_name", "phone", "email", "credit_limit", "is_active", "created_at")
    list_filter = ("gender", "is_active", "created_at")
    search_fields = ("full_name", "phone", "email")
