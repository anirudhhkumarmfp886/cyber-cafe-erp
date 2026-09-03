"""
InventoryService — the only place stock items and movements change.

Business rules enforced here:
- Item names must be unique (case-insensitive).
- Reorder level cannot be negative.
- Stock-in (purchase) recalculates weighted average cost and optionally
  books a PURCHASE expense in the Cash Book.
- Stock-out validates that sufficient stock exists before decrementing.
- Adjustments set stock to a new physical-count value and record a
  movement for the delta (positive or negative).
"""
from decimal import Decimal

from django.db import transaction

from apps.common.services.reference_service import ReferenceService
from apps.finance.models.enums import CashEntryCategory, PaymentMode
from apps.finance.services.cashbook_service import CashBookService
from apps.inventory.models import StockItem, StockMovement
from apps.inventory.models.enums import MovementType, OUTBOUND_TYPES


class InventoryService:
    # ------------------------------------------------------------------
    # Item CRUD
    # ------------------------------------------------------------------
    @staticmethod
    def create_item(*, data: dict, by=None) -> StockItem:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Item name is required.")
        if StockItem.objects.filter(name__iexact=name).exists():
            raise ValueError("An item with this name already exists.")

        reorder_level = data.get("reorder_level")
        if reorder_level is not None and Decimal(str(reorder_level)) < 0:
            raise ValueError("Reorder level cannot be negative.")

        sku = str(data.get("sku") or "").strip() or None
        if sku and StockItem.objects.filter(sku=sku).exists():
            raise ValueError("An item with this SKU already exists.")

        return StockItem.objects.create(
            name=name,
            sku=sku,
            category=str(data.get("category", "")).strip(),
            unit=data.get("unit", "PIECE"),
            reorder_level=reorder_level if reorder_level is not None else 5,
            description=str(data.get("description", "")).strip(),
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    def update_item(item: StockItem, *, data: dict, by=None) -> StockItem:
        name = str(data.get("name", "")).strip()
        if name:
            dup = StockItem.objects.filter(name__iexact=name).exclude(pk=item.pk)
            if dup.exists():
                raise ValueError("An item with this name already exists.")
            item.name = name

        sku = data.get("sku")
        if sku is not None:
            sku = str(sku).strip() or None
            if sku:
                dup = StockItem.objects.filter(sku=sku).exclude(pk=item.pk)
                if dup.exists():
                    raise ValueError("An item with this SKU already exists.")
            item.sku = sku

        reorder_level = data.get("reorder_level")
        if reorder_level is not None:
            if Decimal(str(reorder_level)) < 0:
                raise ValueError("Reorder level cannot be negative.")
            item.reorder_level = reorder_level

        for field in ("category", "unit", "description"):
            if field in data:
                setattr(item, field, data[field])

        item.updated_by = by
        item.save()
        return item

    @staticmethod
    def deactivate_item(item: StockItem, *, by=None) -> StockItem:
        return item.soft_delete(by=by)

    @staticmethod
    def restore_item(item: StockItem, *, by=None) -> StockItem:
        return item.restore(by=by)

    # ------------------------------------------------------------------
    # Stock In (Purchase)
    # ------------------------------------------------------------------
    @staticmethod
    def stock_in(
        item: StockItem,
        *,
        quantity,
        unit_cost,
        movement_date=None,
        supplier_name: str = "",
        payment_mode: str = "",
        notes: str = "",
        by=None,
    ) -> StockMovement:
        """Record a purchase: increase stock, recalculate WAC, optionally
        book a PURCHASE expense in the Cash Book."""
        quantity = Decimal(str(quantity))
        unit_cost = Decimal(str(unit_cost))

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if unit_cost < 0:
            raise ValueError("Unit cost cannot be negative.")

        total_cost = quantity * unit_cost

        with transaction.atomic():
            # Weighted Average Cost recalculation
            old_stock = item.current_stock
            old_cost = item.unit_cost
            new_stock = old_stock + quantity
            if new_stock > 0:
                item.unit_cost = (old_stock * old_cost + total_cost) / new_stock
            item.current_stock = new_stock
            item.save(update_fields=["current_stock", "unit_cost", "updated_at"])

            # Resolve staff from the acting user
            staff = None
            if by is not None:
                staff = getattr(by, "employee", None)

            # Optional Cash Book integration
            cash_entry = None
            if payment_mode and payment_mode in dict(PaymentMode.choices):
                cash_entry = CashBookService.record_expense(
                    amount=total_cost,
                    category=CashEntryCategory.PURCHASE,
                    payment_mode=payment_mode,
                    party_name=supplier_name or item.name,
                    description=f"Stock purchase: {item.name} × {quantity}",
                    entry_date=movement_date,
                    by=by,
                    staff=staff,
                )

            movement = StockMovement.objects.create(
                reference_number=ReferenceService.next(ReferenceService.STOCK),
                item=item,
                movement_type=MovementType.PURCHASE,
                quantity=quantity,
                unit_cost=unit_cost,
                total_cost=total_cost,
                movement_date=movement_date or __import__("datetime").date.today(),
                supplier_name=supplier_name,
                staff=staff,
                cash_entry=cash_entry,
                notes=notes,
                created_by=by,
                updated_by=by,
            )
            return movement

    # ------------------------------------------------------------------
    # Stock Out (Issue / Damage / Return)
    # ------------------------------------------------------------------
    @staticmethod
    def stock_out(
        item: StockItem,
        *,
        quantity,
        movement_type: str = MovementType.ISSUE,
        reason: str = "",
        movement_date=None,
        notes: str = "",
        by=None,
    ) -> StockMovement:
        """Record a stock-out: decrease stock, validate sufficiency."""
        quantity = Decimal(str(quantity))

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if movement_type not in OUTBOUND_TYPES:
            raise ValueError(f"Invalid outbound movement type: {movement_type}")
        if item.current_stock < quantity:
            raise ValueError(
                f"Insufficient stock. Available: {item.current_stock}, requested: {quantity}."
            )

        with transaction.atomic():
            item.current_stock -= quantity
            item.save(update_fields=["current_stock", "updated_at"])

            staff = None
            if by is not None:
                staff = getattr(by, "employee", None)

            movement = StockMovement.objects.create(
                reference_number=ReferenceService.next(ReferenceService.STOCK),
                item=item,
                movement_type=movement_type,
                quantity=quantity,
                unit_cost=item.unit_cost,
                total_cost=quantity * item.unit_cost,
                movement_date=movement_date or __import__("datetime").date.today(),
                reason=reason,
                staff=staff,
                notes=notes,
                created_by=by,
                updated_by=by,
            )
            return movement

    # ------------------------------------------------------------------
    # Adjustment (Physical Count)
    # ------------------------------------------------------------------
    @staticmethod
    def adjust_stock(
        item: StockItem,
        *,
        new_quantity,
        reason: str = "",
        by=None,
    ) -> StockMovement:
        """Set stock to a new physical-count value by recording an
        adjustment movement for the delta."""
        new_quantity = Decimal(str(new_quantity))
        if new_quantity < 0:
            raise ValueError("Stock quantity cannot be negative.")

        delta = new_quantity - item.current_stock
        if delta == 0:
            raise ValueError("New quantity is the same as current stock. No adjustment needed.")

        with transaction.atomic():
            item.current_stock = new_quantity
            item.save(update_fields=["current_stock", "updated_at"])

            staff = None
            if by is not None:
                staff = getattr(by, "employee", None)

            movement = StockMovement.objects.create(
                reference_number=ReferenceService.next(ReferenceService.STOCK),
                item=item,
                movement_type=MovementType.ADJUSTMENT,
                quantity=abs(delta),
                unit_cost=item.unit_cost,
                total_cost=abs(delta) * item.unit_cost,
                movement_date=__import__("datetime").date.today(),
                reason=reason or f"Adjusted from {item.current_stock + delta * -1} to {new_quantity}",
                staff=staff,
                notes=f"Delta: {'+' if delta > 0 else ''}{delta}",
                created_by=by,
                updated_by=by,
            )
            return movement
