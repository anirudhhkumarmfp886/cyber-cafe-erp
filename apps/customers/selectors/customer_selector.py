"""
CustomerSelector — read-only access to customer data for views/templates.
"""
from django.db.models import Q

from apps.customers.models import Customer


class CustomerSelector:
    @staticmethod
    def list_customers(search: str = ""):
        queryset = Customer.objects.all()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return queryset.order_by("-created_at")

    @staticmethod
    def get_by_id(customer_id):
        return Customer.objects.filter(id=customer_id).first()

    @staticmethod
    def count_active() -> int:
        return Customer.objects.count()
