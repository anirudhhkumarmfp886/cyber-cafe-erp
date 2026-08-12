"""
Shared admin helpers.

Concrete model admins register a subclass of BaseAdmin; the mixin wires
common list behaviour (read-only audit columns), a "Show deleted" toggle
that lets superusers browse the soft-delete trash, and restore/purge
actions. Hard deletes in the admin are only possible through the explicit
``hard_delete`` action; the standard delete buttons stay disabled so a
plain misclick can never destroy data.
"""
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db.models.deletion import ProtectedError
from django.urls import reverse


class BaseAdmin(admin.ModelAdmin):
    """Common admin behaviour for soft-deletable models."""

    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at", "deleted_by")

    actions = ("hard_delete", "restore_deleted")

    def save_model(self, request, obj, form, change):
        # CurrentUserMiddleware already handles created_by/updated_by, but
        # admin actions run through the normal request cycle so nothing
        # extra is needed here beyond a safe fallback.
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        # Soft-delete only in the admin; hard deletes are banned except
        # through the explicit hard_delete action.
        return False

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.soft_delete(by=request.user)

    # ------------------------------------------------------------------
    # "Show deleted" toggle
    # ------------------------------------------------------------------
    def get_queryset(self, request):
        """Return only active rows by default; deleted rows when toggled."""
        if getattr(request, "show_deleted", False):
            return self.model.all_objects.filter(deleted_at__isnull=False)
        return super().get_queryset(request)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        original_get = request.GET.copy()
        show_deleted = original_get.get("deleted") == "1"
        # Strip the toggle param before the ChangeList parses GET as field
        # lookups — otherwise Django treats "deleted" as a model lookup and
        # bounces to ?e=1 (IncorrectLookupParameters). get_queryset learns
        # the toggle state from the request flag instead of the GET param.
        request.show_deleted = show_deleted
        request.GET = original_get.copy()
        request.GET.pop("deleted", None)
        extra_context["show_deleted"] = show_deleted
        extra_context["show_deleted_toggle"] = True
        extra_context["deleted_toggle_url"] = self._deleted_toggle_url(original_get)
        return super().changelist_view(request, extra_context=extra_context)

    def _deleted_toggle_url(self, params):
        """Changelist URL with the ``deleted`` flag flipped, keeping filters."""
        params = params.copy()
        if params.get("deleted") == "1":
            params.pop("deleted", None)
        else:
            params["deleted"] = "1"
        base = reverse(
            "admin:%s_%s_changelist" % (self.model._meta.app_label, self.model._meta.model_name)
        )
        querystring = params.urlencode()
        return f"{base}?{querystring}" if querystring else base

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    @admin.action(
        description="Purge selected soft-deleted records (permanent hard delete, cannot be undone)"
    )
    def hard_delete(self, request, queryset):
        """Permanently remove soft-deleted rows; active rows are soft-deleted.

        The standard admin has no delete button, so this action doubles as
        the only way to trash (soft-delete) an active record from the admin.
        Rows that are already soft-deleted are removed from the database
        entirely — this is irreversible.

        The action reads the selected pks straight from the POST (not from
        ``queryset``, which is limited to the currently visible view) so it
        works in both the active and the "Show deleted" changelist.
        """
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        objs = self.model.all_objects.filter(pk__in=selected)
        purged = 0
        trashed = 0
        blocked = 0
        for obj in objs:
            if obj.deleted_at is None:
                obj.soft_delete(by=request.user)
                trashed += 1
                continue
            try:
                obj.delete()
                purged += 1
            except ProtectedError:
                blocked += 1

        parts = []
        if purged:
            parts.append(f"{purged} permanently deleted")
        if trashed:
            parts.append(f"{trashed} soft-deleted (were still active)")
        if blocked:
            parts.append(f"{blocked} skipped — blocked by related records")
        summary = "; ".join(parts) if parts else "Nothing deleted."
        level = messages.WARNING if blocked else messages.SUCCESS
        self.message_user(request, f"Hard delete: {summary}", level=level)

    @admin.action(description="Restore selected soft-deleted records")
    def restore_deleted(self, request, queryset):
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        objs = self.model.all_objects.filter(pk__in=selected)
        restored = 0
        skipped = 0
        for obj in objs:
            if obj.deleted_at is None:
                skipped += 1
                continue
            obj.restore(by=request.user)
            restored += 1
        message = f"Restored {restored} record(s)."
        if skipped:
            message += f" {skipped} skipped — they were not deleted."
        self.message_user(request, message)
