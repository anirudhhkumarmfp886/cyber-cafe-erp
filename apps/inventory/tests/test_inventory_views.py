"""Tests for inventory views (permission gates, GET/POST flows)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.inventory.models import StockItem, StockMovement
from apps.inventory.services.inventory_service import InventoryService

User = get_user_model()


class InventoryViewTestMixin:
    """Shared setUp for view tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="owner", password="Pass#123", is_superuser=True)
        self.client.login(username="owner", password="Pass#123")

    def _create_item(self, name="A4 Paper"):
        return InventoryService.create_item(data={"name": name}, by=self.user)


class StockItemListViewTests(InventoryViewTestMixin, TestCase):
    def test_list_page_loads(self):
        response = self.client.get(reverse("inventory:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory")

    def test_create_item_via_post(self):
        response = self.client.post(reverse("inventory:list"), {
            "name": "Ink Cartridge",
            "unit": "PIECE",
            "reorder_level": 3,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StockItem.objects.filter(name="Ink Cartridge").exists())

    def test_search_filter(self):
        self._create_item("A4 Paper")
        self._create_item("Toner")
        response = self.client.get(reverse("inventory:list"), {"q": "toner"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Toner")
        self.assertNotContains(response, "A4 Paper")


class StockItemDetailViewTests(InventoryViewTestMixin, TestCase):
    def test_detail_page_loads(self):
        item = self._create_item()
        response = self.client.get(reverse("inventory:detail", kwargs={"pk": item.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A4 Paper")

    def test_detail_shows_movements(self):
        item = self._create_item()
        InventoryService.stock_in(item, quantity=50, unit_cost=5, by=self.user)
        response = self.client.get(reverse("inventory:detail", kwargs={"pk": item.pk}))
        self.assertContains(response, "STK-")
        self.assertContains(response, "Purchase")


class StockInViewTests(InventoryViewTestMixin, TestCase):
    def test_stock_in_get(self):
        item = self._create_item()
        response = self.client.get(reverse("inventory:stock_in", kwargs={"pk": item.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock In")

    def test_stock_in_post(self):
        item = self._create_item()
        response = self.client.post(reverse("inventory:stock_in", kwargs={"pk": item.pk}), {
            "quantity": "100",
            "unit_cost": "5.00",
            "supplier_name": "Stationery Shop",
        })
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal("100"))

    def test_stock_in_with_cash_book(self):
        item = self._create_item()
        self.client.post(reverse("inventory:stock_in", kwargs={"pk": item.pk}), {
            "quantity": "10",
            "unit_cost": "20.00",
            "payment_mode": "CASH",
        })
        movement = StockMovement.objects.first()
        self.assertIsNotNone(movement.cash_entry)


class StockOutViewTests(InventoryViewTestMixin, TestCase):
    def test_stock_out_get(self):
        item = self._create_item()
        InventoryService.stock_in(item, quantity=50, unit_cost=5, by=self.user)
        response = self.client.get(reverse("inventory:stock_out", kwargs={"pk": item.pk}))
        self.assertEqual(response.status_code, 200)

    def test_stock_out_post(self):
        item = self._create_item()
        InventoryService.stock_in(item, quantity=50, unit_cost=5, by=self.user)
        response = self.client.post(reverse("inventory:stock_out", kwargs={"pk": item.pk}), {
            "quantity": "20",
            "movement_type": "ISSUE",
            "reason": "Counter 1 use",
        })
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal("30"))

    def test_stock_out_insufficient(self):
        item = self._create_item()
        InventoryService.stock_in(item, quantity=10, unit_cost=5, by=self.user)
        response = self.client.post(reverse("inventory:stock_out", kwargs={"pk": item.pk}), {
            "quantity": "100",
            "movement_type": "ISSUE",
        })
        # Should show error, not redirect
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insufficient stock")


class AdjustViewTests(InventoryViewTestMixin, TestCase):
    def test_adjust_post(self):
        item = self._create_item()
        InventoryService.stock_in(item, quantity=50, unit_cost=5, by=self.user)
        response = self.client.post(reverse("inventory:adjust", kwargs={"pk": item.pk}), {
            "new_quantity": "45",
            "reason": "Physical count",
        })
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal("45"))


class LowStockViewTests(InventoryViewTestMixin, TestCase):
    def test_low_stock_page_loads(self):
        response = self.client.get(reverse("inventory:low_stock"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low Stock")

    def test_low_stock_shows_items(self):
        self._create_item()  # stock=0, reorder=5 → low stock
        response = self.client.get(reverse("inventory:low_stock"))
        self.assertContains(response, "A4 Paper")


class PermissionGateTests(TestCase):
    """Non-superuser without inventory permissions gets 403."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="staff", password="Pass#123")
        self.client.login(username="staff", password="Pass#123")

    def test_list_requires_permission(self):
        response = self.client.get(reverse("inventory:list"))
        self.assertEqual(response.status_code, 403)

    def test_stock_in_requires_permission(self):
        su = User.objects.create_superuser(username="su", password="Pass#123")
        item = InventoryService.create_item(data={"name": "Paper"}, by=su)
        response = self.client.get(reverse("inventory:stock_in", kwargs={"pk": item.pk}))
        self.assertEqual(response.status_code, 403)
