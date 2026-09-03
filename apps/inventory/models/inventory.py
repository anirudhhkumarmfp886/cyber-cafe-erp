"""
Inventory models — stock items and their movement ledger.

A StockItem is a consumable the cafe keeps in stock (A4 paper, ink
cartridges, toner, snacks, stationery). Every physical movement of
stock — purchase, issue to a counter, damage write-off, adjustment
after a physical count — is recorded as an append-only StockMovement
row so the stock history is fully auditable.

Stock valuation uses **Weighted Average Cost (WAC)**. On every
purchase (stock-in) the item's ``unit_cost`` is recalculated:

    new_cost = (old_stock × old_cost + new_qty × purchase_cost)
             / (old_stock + new_qty)

``current_stock`` is maintained on every movement (increment on
purchase, decrement on issue/damage/return). A ``reorder_level``
field enables low-stock alerting on the dashboard and a dedicated
low-stock page.
"""
from datetime import date

from django.db import models

from apps.common.models import BaseModel, money_field
from apps.employees.models import Employee
from apps.inventory.models.enums import MovementType, UnitType


class StockItem(BaseModel):
    """A consumable item stocked by the cafe."""

    name = models.CharField(max_length=150, unique=True, db_index=True)
    sku = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text="Optional SKU or barcode.",
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Free-form category, e.g. Paper, Ink, Snacks.",
    )
    unit = models.CharField(
        max_length=20,
        choices=UnitType.choices,
        default=UnitType.PIECE,
    )
    current_stock = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Current quantity in stock. Updated on every movement.",
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=5,
        help_text="Low-stock alert fires when current_stock falls to or below this level.",
    )
    unit_cost = money_field(
        default=0,
        help_text="Weighted average cost per unit. Recalculated on every purchase.",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Stock Item"
        verbose_name_plural = "Stock Items"
        indexes = [
            models.Index(fields=["category", "name"]),
            models.Index(fields=["current_stock", "reorder_level"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.current_stock} {self.get_unit_display()})"

    @property
    def is_low_stock(self) -> bool:
        return self.current_stock <= self.reorder_level

    @property
    def stock_value(self):
        """Total value of current stock at weighted average cost."""
        return self.current_stock * self.unit_cost


class StockMovement(BaseModel):
    """Append-only ledger of every stock movement."""

    reference_number = models.CharField(
        max_length=30, unique=True, editable=False, db_index=True,
    )
    item = models.ForeignKey(
        StockItem,
        on_delete=models.CASCADE,
        related_name="movements",
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        db_index=True,
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Always positive; direction is inferred from movement_type.",
    )
    unit_cost = money_field(
        default=0,
        help_text="Cost per unit at this movement.",
    )
    total_cost = money_field(
        default=0,
        help_text="quantity × unit_cost.",
    )
    movement_date = models.DateField(default=date.today, db_index=True)
    supplier_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Supplier / vendor name (for purchases).",
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason or note, e.g. 'Issued to Counter 1', 'Damaged in transit'.",
    )
    staff = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
        help_text="Staff member who handled this movement.",
    )
    cash_entry = models.ForeignKey(
        "finance.CashBookEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
        help_text="Linked cash book expense for purchase movements.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-movement_date", "-created_at"]
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        indexes = [
            models.Index(fields=["item", "movement_date"]),
            models.Index(fields=["movement_type", "movement_date"]),
        ]

    def __str__(self):
        return f"{self.reference_number} {self.get_movement_type_display()} {self.quantity} × {self.item.name}"
