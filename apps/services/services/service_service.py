"""
ServiceService — the only place services and their price history change.

Creating a service also records the opening price. Editing the price is
append-only: the current price moves, and a ServicePriceHistory row is
added so every past bill can be explained.

Categories are free-form: the owner can pick an existing ``Category`` or
type a new one (the legacy choice codes GAMES / INTERNET / ... are mapped
onto their seeded display names for backwards compatibility). Custom fields
are owner-managed dynamic inputs captured on the bill for a service.
"""
from datetime import date

from apps.services.models import (
    Category,
    CustomFieldType,
    Service,
    ServiceCustomField,
    ServicePriceHistory,
)

_EDITABLE_FIELDS = ("name", "unit", "price", "description")

_LEGACY_CATEGORIES = {
    "GAMES": "Games",
    "INTERNET": "Internet",
    "PRINTING": "Printing",
    "RECHARGE": "Recharge",
    "SNACKS": "Snacks",
    "OTHER": "Other",
}


def _normalize_category_name(name: str) -> str:
    name = name.strip()
    if name.upper() in _LEGACY_CATEGORIES:
        return _LEGACY_CATEGORIES[name.upper()]
    return name


def _resolve_category(data: dict):
    """Return a Category from ``new_category`` / ``category`` / default."""
    new_name = str(data.get("new_category") or "").strip()
    if new_name:
        return Category.objects.get_or_create(name=_normalize_category_name(new_name))[0]

    category = data.get("category")
    if isinstance(category, Category):
        return category
    name = str(category or "").strip()
    if not name:
        return Category.objects.get_or_create(name="Other")[0]
    return Category.objects.get_or_create(name=_normalize_category_name(name))[0]


class ServiceService:
    @staticmethod
    def create_service(*, data: dict, by=None, effective_from=None) -> Service:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Service name is required.")

        price = data.get("price")
        if price is None or price <= 0:
            raise ValueError("Price must be greater than zero.")

        if Service.objects.filter(name__iexact=name).exists():
            raise ValueError("A service with this name already exists.")

        effective_from = effective_from or date.today()
        service = Service.objects.create(
            name=name,
            category=_resolve_category(data),
            unit=data.get("unit", ""),
            price=price,
            description=data.get("description", ""),
            created_by=by,
            updated_by=by,
        )
        ServicePriceHistory.objects.create(
            service=service,
            price=price,
            effective_from=effective_from,
            notes="Initial price",
            created_by=by,
            updated_by=by,
        )
        return service

    @staticmethod
    def update_service(service: Service, *, data: dict, by=None, effective_from=None) -> Service:
        for field in _EDITABLE_FIELDS:
            if field in data:
                setattr(service, field, data[field])

        new_category = data.get("new_category")
        category = data.get("category")
        if new_category or category:
            service.category = _resolve_category(data)

        new_price = service.price
        if new_price is None or new_price <= 0:
            raise ValueError("Price must be greater than zero.")

        price_changed = (
            not service.price_history.exists() or service.price_history.first().price != new_price
        )
        service.updated_by = by
        service.save()

        if price_changed:
            ServicePriceHistory.objects.create(
                service=service,
                price=new_price,
                effective_from=effective_from or date.today(),
                notes="Price updated",
                created_by=by,
                updated_by=by,
            )
        return service

    @staticmethod
    def deactivate_service(service: Service, *, by=None) -> Service:
        return service.soft_delete(by=by)

    @staticmethod
    def restore_service(service: Service, *, by=None) -> Service:
        return service.restore(by=by)

    @staticmethod
    def create_custom_field(service: Service, *, data: dict, by=None) -> ServiceCustomField:
        label = str(data.get("label", "")).strip()
        if not label:
            raise ValueError("Field label is required.")

        roles = [code for code in data.get("roles", []) if code]
        return ServiceCustomField.objects.create(
            service=service,
            label=label,
            field_type=data.get("field_type") or CustomFieldType.TEXT,
            required=bool(data.get("required")),
            help_text=str(data.get("help_text", "")).strip(),
            roles=",".join(roles),
            ordering=int(data.get("ordering") or 0),
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    def delete_custom_field(field: ServiceCustomField, *, by=None) -> ServiceCustomField:
        return field.soft_delete(by=by)
