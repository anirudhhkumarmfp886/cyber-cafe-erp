"""
Default managers for every model.

Every project model inherits from ``BaseModel`` and therefore gets two
managers:

    Model.objects      -> ActiveManager:   only records not soft-deleted
    Model.all_objects  -> AllObjectsManager: every record (including deleted)

Business rules should read through ``objects`` (active data only) and
audit/restore flows through ``all_objects``.
"""
from django.db import models


class ActiveManager(models.Manager):
    """Returns records that have not been soft-deleted."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """Returns every record, including soft-deleted ones."""

    def get_queryset(self):
        return super().get_queryset()
