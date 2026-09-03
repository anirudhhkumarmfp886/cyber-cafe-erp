"""
InventorySelector — read-only access to the stock catalog and movements.

Queries live here (never in views or templates).
"""
from decimal import Decimal

from django.db.models import F, Q, Sum

from apps.inventory.models import StockItem


class InventorySelector:
    @staticmethod
    def list_items(filters: dict | None = None):
        """Return active stock items, optionally filtered by search and category."""
        filters = filters or {}
        queryset = StockItem.objects.order_by("category", "name")

        q = str(filters.get("q", "")).strip()
        if q:
            queryset = queryset.filter(
                Q(name__icontains=q) | Q(sku__icontains=q) | Q(category__icontains=q)
            )

        category = str(filters.get("category", "")).strip()
        if category:
            queryset = queryset.filter(category__iexact=category)

        return queryset

    @staticmethod
    def get_by_id(item_id):
        return StockItem.objects.filter(id=item_id).first()

    @staticmethod
    def low_stock_items():
        """Items where current_stock <= reorder_level."""
        return StockItem.objects.filter(
            current_stock__lte=F("reorder_level"),
        ).order_by("current_stock")

    @staticmethod
    def count_active() -> int:
        return StockItem.objects.count()

    @staticmethod
    def count_low_stock() -> int:
        return StockItem.objects.filter(
            current_stock__lte=F("reorder_level"),
        ).count()

    @staticmethod
    def total_stock_value() -> Decimal:
        """Sum of (current_stock × unit_cost) for all active items."""
        result = StockItem.objects.aggregate(
            total=Sum(F("current_stock") * F("unit_cost"))
        )["total"]
        return result or Decimal("0.00")

    @staticmethod
    def movement_history(item: StockItem, limit: int = 50):
        """Movement ledger for a specific item, most recent first."""
        return item.movements.select_related("staff", "cash_entry").order_by(
            "-movement_date", "-created_at"
        )[:limit]

    @staticmethod
    def categories() -> list[str]:
        """Distinct non-empty categories in use."""
        return list(
            StockItem.objects.exclude(category="")
            .values_list("category", flat=True)
            .distinct()
            .order_by("category")
        )
