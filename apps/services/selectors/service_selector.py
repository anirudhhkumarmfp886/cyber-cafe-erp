"""
ServiceSelector — read-only access to the service catalog.

Queries live here (never in views or templates). Custom-field visibility is
role-based: a staff member only sees fields whose ``roles`` list contains
their role (or whose role list is empty = everyone).
"""
from django.db.models import Q

from apps.employees.models import Role
from apps.services.models import Category, Service


class ServiceSelector:
    @staticmethod
    def list_services(filters: dict):
        queryset = Service.objects.select_related("category").order_by("category__name", "name")
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
        return Category.objects.order_by("name")

    @staticmethod
    def count_active() -> int:
        return Service.objects.count()

    @staticmethod
    def user_role(user) -> str:
        """Return the user's role code; superusers count as Owner."""
        if user.is_superuser:
            return Role.OWNER
        employee = getattr(user, "employee", None)
        return employee.role if employee and employee.role else Role.STAFF

    @staticmethod
    def visible_custom_fields(service, user):
        """Fields the user's role is allowed to see and fill."""
        role = ServiceSelector.user_role(user)
        fields = service.custom_fields.filter(is_active=True)
        allowed = []
        for field in fields:
            role_list = field.role_list()
            if not role_list or role in role_list:
                allowed.append(field)
        return allowed

    @staticmethod
    def custom_field_payload(service, user):
        """JSON-safe payload for the billing screen's dynamic form rows."""
        payload = []
        for field in ServiceSelector.visible_custom_fields(service, user):
            item = {
                "id": str(field.pk),
                "variable_name": field.variable_name,
                "label": field.label,
                "field_type": field.field_type,
                "required": field.required,
                "help_text": field.help_text,
            }
            if field.field_type == "BANK_ACCOUNT":
                item["bank_accounts"] = [
                    {"id": str(acc.pk), "name": f"{acc.account_name} ({acc.bank_name})"}
                    for acc in ServiceSelector.bank_accounts()
                ]
            payload.append(item)
        return payload

    @staticmethod
    def bank_accounts():
        from apps.finance.models import BankAccount

        return BankAccount.objects.select_related().order_by("account_name")
