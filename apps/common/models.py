"""
BaseModel — the single audit/soft-delete foundation for the whole ERP.

Every model inherits from BaseModel. It provides:

    id          UUID primary key (collision-safe, non-sequential)
    created_at  / updated_at            automatic timestamps
    created_by  / updated_by            audit FKs to the current user
    is_active   active flag (indexed)
    deleted_at  / deleted_by            soft-delete markers

Audit FKs are filled automatically by CurrentUserMiddleware on every
request (see apps.common.middleware). Outside a request context they
stay NULL, which is acceptable for scripts and shell sessions.

The default manager ``objects`` hides soft-deleted rows; ``all_objects``
exposes everything for restore/audit workflows.
"""
import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.common.managers import ActiveManager, AllObjectsManager
from apps.common.middleware import get_current_user


def money_field(**kwargs):
    """A DecimalField configured with the ERP's single money precision.

    Use this for every monetary column so the whole system agrees on
    width and rounding.
    """
    defaults = {
        "max_digits": settings.MONEY_MAX_DIGITS,
        "decimal_places": settings.MONEY_DECIMAL_PLACES,
    }
    defaults.update(kwargs)
    return models.DecimalField(**defaults)


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    is_active = models.BooleanField(default=True, db_index=True)

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Auto-fill audit fields from the thread-local current user."""
        user = get_current_user()
        if self._state.adding:
            if user and not self.created_by_id:
                self.created_by = user
            if user and not self.updated_by_id:
                self.updated_by = user
        else:
            if user:
                self.updated_by = user
        super().save(*args, **kwargs)

    def soft_delete(self, *, by=None, commit: bool = True) -> "BaseModel":
        """Mark the record as deleted without removing it from the database."""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.deleted_by = by or get_current_user()
        self.updated_by = by or get_current_user()
        if commit:
            self.save(update_fields=["is_active", "deleted_at", "deleted_by", "updated_by", "updated_at"])
        return self

    def restore(self, *, by=None, commit: bool = True) -> "BaseModel":
        """Bring a soft-deleted record back into active use."""
        self.is_active = True
        self.deleted_at = None
        self.deleted_by = None
        self.updated_by = by or get_current_user()
        if commit:
            self.save(update_fields=["is_active", "deleted_at", "deleted_by", "updated_by", "updated_at"])
        return self


class Sequence(BaseModel):
    """Monotonic counter used to mint gapless reference numbers.

    ``ReferenceService.next()`` locks the row (select_for_update) inside a
    transaction and increments it, so concurrent requests can never mint the
    same number. Every financial record carries one of these reference
    numbers for the audit trail.
    """

    name = models.CharField(max_length=20, unique=True, db_index=True)
    last_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        verbose_name = "Sequence"
        verbose_name_plural = "Sequences"

    def __str__(self):
        return f"{self.name}: {self.last_value}"

    @classmethod
    def next(cls, name: str) -> int:
        """Atomically advance the counter for ``name`` and return its value."""
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(name=name)
            seq.last_value += 1
            seq.save(update_fields=["last_value", "updated_at"])
            return seq.last_value
