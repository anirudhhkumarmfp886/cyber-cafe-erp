"""
ServiceService — the only place services and their price history change.

Creating a service also records the opening price. Editing the price is
append-only: the current price moves, and a ServicePriceHistory row is
added so every past bill can be explained.
"""
from datetime import date

from apps.services.models import Service, ServiceCategory, ServicePriceHistory

_EDITABLE_FIELDS = ("name", "category", "unit", "price", "description")


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
            category=data.get("category") or ServiceCategory.OTHER,
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
