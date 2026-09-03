"""Admin configuration for the inventory app."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.inventory.models import StockItem, StockMovement


@admin.register(StockItem)
class StockItemAdmin(BaseAdmin):
    list_display = ("name", "sku", "category", "unit", "current_stock", "reorder_level", "unit_cost", "is_active")
    list_filter = ("category", "unit", "is_active")
    search_fields = ("name", "sku", "category")


@admin.register(StockMovement)
class StockMovementAdmin(BaseAdmin):
    list_display = (
        "reference_number", "item", "movement_type", "quantity",
        "unit_cost", "total_cost", "movement_date", "supplier_name",
    )
    list_filter = ("movement_type", "movement_date")
    search_fields = ("reference_number", "item__name", "supplier_name", "reason")
    autocomplete_fields = ("item",)
