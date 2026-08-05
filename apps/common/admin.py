"""
Shared admin helpers.

Concrete model admins register a subclass of BaseAdmin; the mixin wires
common list behaviour (read-only audit columns) and prevents accidental
hard deletes in the admin.
"""
from django.contrib import admin


class BaseAdmin(admin.ModelAdmin):
    """Common admin behaviour for soft-deletable models."""

    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at", "deleted_by")

    def save_model(self, request, obj, form, change):
        # CurrentUserMiddleware already handles created_by/updated_by, but
        # admin actions run through the normal request cycle so nothing
        # extra is needed here beyond a safe fallback.
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        # Soft-delete only in the admin; hard deletes are banned.
        return False

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.soft_delete(by=request.user)
