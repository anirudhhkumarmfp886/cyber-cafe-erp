"""
Management command: Check low stock items and log/output alert message.

Usage:
    python manage.py send_low_stock_alerts
    python manage.py send_low_stock_alerts --phone 9876543210
"""
from django.core.management.base import BaseCommand

from apps.common.services.notification_service import NotificationService
from apps.inventory.selectors.inventory_selector import InventorySelector


class Command(BaseCommand):
    help = "Generate and output low stock alert message for the owner."

    def add_arguments(self, parser):
        parser.add_argument(
            "--phone",
            type=str,
            help="Owner phone number to generate a direct WhatsApp link.",
        )

    def handle(self, *args, **options):
        items = list(InventorySelector.low_stock_items())
        count = len(items)
        if not count:
            self.stdout.write(self.style.SUCCESS("All items are sufficiently stocked. No low-stock alerts."))
            return

        self.stdout.write(self.style.WARNING(f"Found {count} item(s) below reorder level:"))
        for item in items:
            self.stdout.write(f"  - {item.name}: {item.current_stock} (reorder at {item.reorder_level})")

        msg = NotificationService.format_low_stock_summary(items)
        self.stdout.write("\n--- Alert Summary ---")
        self.stdout.write(msg)

        phone = options.get("phone")
        whatsapp_url = NotificationService.get_low_stock_whatsapp_url(items, owner_phone=phone)
        self.stdout.write(f"\nWhatsApp Link:\n{whatsapp_url}")
