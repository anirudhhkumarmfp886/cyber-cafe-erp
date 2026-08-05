"""Admin configuration for employees."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.employees.models import Employee


@admin.register(Employee)
class EmployeeAdmin(BaseAdmin):
    list_display = ("employee_code", "full_name", "role", "status", "is_active", "created_at")
    list_filter = ("role", "status", "is_active")
    search_fields = ("employee_code", "full_name", "user__username", "personal_phone")
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
