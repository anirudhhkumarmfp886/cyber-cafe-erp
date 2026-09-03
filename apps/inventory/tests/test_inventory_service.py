"""Tests for the inventory service layer (business rules)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import CashBookEntry
from apps.inventory.models import StockItem
from apps.inventory.services.inventory_service import InventoryService

User = get_user_model()


class InventoryItemCRUDTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")

    def test_create_item_minimal(self):
        item = InventoryService.create_item(data={"name": "A4 Paper"}, by=self.user)
        self.assertEqual(item.name, "A4 Paper")
        self.assertEqual(item.current_stock, 0)
        self.assertEqual(item.reorder_level, 5)
        self.assertEqual(item.unit, "PIECE")
        self.assertTrue(item.is_active)

    def test_create_item_full(self):
        item = InventoryService.create_item(data={
            "name": "Ink Cartridge HP 802",
            "sku": "INK-802",
            "category": "Ink",
            "unit": "PIECE",
            "reorder_level": 3,
            "description": "Black ink cartridge",
        }, by=self.user)
        self.assertEqual(item.sku, "INK-802")
        self.assertEqual(item.category, "Ink")
        self.assertEqual(item.reorder_level, 3)

    def test_create_requires_name(self):
        with self.assertRaisesMessage(ValueError, "name is required"):
            InventoryService.create_item(data={"name": "  "}, by=self.user)

    def test_create_rejects_duplicate_name(self):
        InventoryService.create_item(data={"name": "A4 Paper"}, by=self.user)
        with self.assertRaisesMessage(ValueError, "already exists"):
            InventoryService.create_item(data={"name": "a4 paper"}, by=self.user)

    def test_create_rejects_duplicate_sku(self):
        InventoryService.create_item(data={"name": "Item A", "sku": "SKU-1"}, by=self.user)
        with self.assertRaisesMessage(ValueError, "SKU already exists"):
            InventoryService.create_item(data={"name": "Item B", "sku": "SKU-1"}, by=self.user)

    def test_create_rejects_negative_reorder(self):
        with self.assertRaisesMessage(ValueError, "Reorder level cannot be negative"):
            InventoryService.create_item(data={"name": "Paper", "reorder_level": -1}, by=self.user)

    def test_update_item(self):
        item = InventoryService.create_item(data={"name": "Paper"}, by=self.user)
        updated = InventoryService.update_item(item, data={
            "name": "A4 Paper 75 GSM", "category": "Paper",
        }, by=self.user)
        updated.refresh_from_db()
        self.assertEqual(updated.name, "A4 Paper 75 GSM")
        self.assertEqual(updated.category, "Paper")

    def test_deactivate_and_restore(self):
        item = InventoryService.create_item(data={"name": "Paper"}, by=self.user)
        InventoryService.deactivate_item(item, by=self.user)
        self.assertFalse(StockItem.objects.filter(pk=item.pk).exists())
        self.assertTrue(StockItem.all_objects.filter(pk=item.pk).exists())
        InventoryService.restore_item(item, by=self.user)
        self.assertTrue(StockItem.objects.filter(pk=item.pk).exists())


class StockInTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")
        self.item = InventoryService.create_item(data={"name": "A4 Paper"}, by=self.user)

    def test_stock_in_increases_stock(self):
        InventoryService.stock_in(
            self.item, quantity=100, unit_cost=5, by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal("100"))
        self.assertEqual(self.item.unit_cost, Decimal("5"))

    def test_stock_in_creates_movement(self):
        movement = InventoryService.stock_in(
            self.item, quantity=50, unit_cost=10, by=self.user,
        )
        self.assertEqual(movement.movement_type, "PURCHASE")
        self.assertEqual(movement.quantity, Decimal("50"))
        self.assertEqual(movement.total_cost, Decimal("500"))
        self.assertTrue(movement.reference_number.startswith("STK-"))

    def test_weighted_average_cost(self):
        """WAC = (old_stock × old_cost + new_qty × new_cost) / (old_stock + new_qty)"""
        InventoryService.stock_in(self.item, quantity=100, unit_cost=5, by=self.user)
        InventoryService.stock_in(self.item, quantity=50, unit_cost=8, by=self.user)
        self.item.refresh_from_db()
        # WAC = (100*5 + 50*8) / (100+50) = 900/150 = 6
        self.assertEqual(self.item.current_stock, Decimal("150"))
        self.assertEqual(self.item.unit_cost, Decimal("6"))

    def test_stock_in_rejects_zero_quantity(self):
        with self.assertRaisesMessage(ValueError, "greater than zero"):
            InventoryService.stock_in(self.item, quantity=0, unit_cost=5, by=self.user)

    def test_stock_in_rejects_negative_cost(self):
        with self.assertRaisesMessage(ValueError, "cannot be negative"):
            InventoryService.stock_in(self.item, quantity=10, unit_cost=-1, by=self.user)

    def test_stock_in_with_cash_book(self):
        """Passing payment_mode books a PURCHASE expense in the cash book."""
        movement = InventoryService.stock_in(
            self.item, quantity=10, unit_cost=20,
            payment_mode="CASH", supplier_name="ABC Stationers",
            by=self.user,
        )
        self.assertIsNotNone(movement.cash_entry)
        entry = movement.cash_entry
        self.assertEqual(entry.entry_type, "EXPENSE")
        self.assertEqual(entry.category, "PURCHASE")
        self.assertEqual(entry.amount, Decimal("200"))
        self.assertEqual(entry.party_name, "ABC Stationers")

    def test_stock_in_without_cash_book(self):
        """No payment_mode means no cash book entry."""
        movement = InventoryService.stock_in(
            self.item, quantity=10, unit_cost=20, by=self.user,
        )
        self.assertIsNone(movement.cash_entry)
        self.assertEqual(CashBookEntry.objects.count(), 0)


class StockOutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")
        self.item = InventoryService.create_item(data={"name": "A4 Paper"}, by=self.user)
        InventoryService.stock_in(self.item, quantity=100, unit_cost=5, by=self.user)
        self.item.refresh_from_db()

    def test_stock_out_decreases_stock(self):
        InventoryService.stock_out(
            self.item, quantity=30, reason="Issued to Counter 1", by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal("70"))

    def test_stock_out_creates_movement(self):
        movement = InventoryService.stock_out(
            self.item, quantity=20, movement_type="ISSUE",
            reason="Daily use", by=self.user,
        )
        self.assertEqual(movement.movement_type, "ISSUE")
        self.assertEqual(movement.quantity, Decimal("20"))
        self.assertEqual(movement.reason, "Daily use")

    def test_stock_out_damage(self):
        movement = InventoryService.stock_out(
            self.item, quantity=5, movement_type="DAMAGE",
            reason="Water damage", by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal("95"))
        self.assertEqual(movement.movement_type, "DAMAGE")

    def test_stock_out_return(self):
        movement = InventoryService.stock_out(
            self.item, quantity=10, movement_type="RETURN",
            reason="Defective batch", by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal("90"))
        self.assertEqual(movement.movement_type, "RETURN")

    def test_stock_out_rejects_insufficient_stock(self):
        with self.assertRaisesMessage(ValueError, "Insufficient stock"):
            InventoryService.stock_out(self.item, quantity=200, by=self.user)

    def test_stock_out_rejects_zero_quantity(self):
        with self.assertRaisesMessage(ValueError, "greater than zero"):
            InventoryService.stock_out(self.item, quantity=0, by=self.user)

    def test_stock_out_rejects_invalid_type(self):
        with self.assertRaisesMessage(ValueError, "Invalid outbound"):
            InventoryService.stock_out(self.item, quantity=5, movement_type="PURCHASE", by=self.user)


class AdjustmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")
        self.item = InventoryService.create_item(data={"name": "Toner"}, by=self.user)
        InventoryService.stock_in(self.item, quantity=50, unit_cost=100, by=self.user)
        self.item.refresh_from_db()

    def test_adjust_stock_up(self):
        movement = InventoryService.adjust_stock(
            self.item, new_quantity=60, reason="Found extra in store room", by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal("60"))
        self.assertEqual(movement.movement_type, "ADJUSTMENT")
        self.assertEqual(movement.quantity, Decimal("10"))  # delta

    def test_adjust_stock_down(self):
        InventoryService.adjust_stock(
            self.item, new_quantity=45, reason="Shrinkage", by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal("45"))

    def test_adjust_rejects_same_quantity(self):
        with self.assertRaisesMessage(ValueError, "same as current stock"):
            InventoryService.adjust_stock(self.item, new_quantity=50, by=self.user)

    def test_adjust_rejects_negative_quantity(self):
        with self.assertRaisesMessage(ValueError, "cannot be negative"):
            InventoryService.adjust_stock(self.item, new_quantity=-5, by=self.user)


class LowStockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")

    def test_is_low_stock_property(self):
        item = InventoryService.create_item(data={
            "name": "Stapler Pins", "reorder_level": 10,
        }, by=self.user)
        self.assertTrue(item.is_low_stock)  # stock = 0 <= reorder = 10
        InventoryService.stock_in(item, quantity=20, unit_cost=1, by=self.user)
        item.refresh_from_db()
        self.assertFalse(item.is_low_stock)  # stock = 20 > reorder = 10

    def test_stock_value_property(self):
        item = InventoryService.create_item(data={"name": "Pens"}, by=self.user)
        InventoryService.stock_in(item, quantity=100, unit_cost=10, by=self.user)
        item.refresh_from_db()
        self.assertEqual(item.stock_value, Decimal("1000"))
