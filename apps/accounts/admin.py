"""Admin configuration for accounts.User."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.common.admin import BaseAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin, BaseAdmin):
    ordering = ("username",)
    list_display = ("username", "get_full_name", "email", "phone", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "email", "phone", "first_name", "last_name")
    readonly_fields = (
        "id",
        "date_joined",
        "last_login",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
        "deleted_by",
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "phone")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        (
            "Audit",
            {
                "classes": ("collapse",),
                "fields": ("id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at", "deleted_by"),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "phone", "password1", "password2"),
            },
        ),
    )
