"""
ServiceSelector — read-only access to the service catalog.
"""
from django.db.models import Q

from apps.services.models import Service, ServiceCategory


class ServiceSelector:
    @staticmethod
    def list_services(filters: dict):
        queryset = Service.objects.select_related().order_by("category", "name")
        category = filters.get("category")
        q = filters.get("q", "")
        if category:
            queryset = queryset.filter(category=category)
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return queryset

    @staticmethod
    def get_by_id(service_id):
        return Service.objects.filter(id=service_id).first()

    @staticmethod
    def price_history(service, limit: int = 100):
        return service.price_history.all()[:limit]

    @staticmethod
    def categories():
        return ServiceCategory.choices

    @staticmethod
    def count_active() -> int:
        return Service.objects.count()
