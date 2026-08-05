"""Tests for the service catalog service layer."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.services.models import Service, ServicePriceHistory
from apps.services.services.service_service import ServiceService

User = get_user_model()


class ServiceServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="boss", password="Pass#123")

    def test_create_service_records_initial_price(self):
        service = ServiceService.create_service(
            data={"name": "Gaming 1hr", "category": "GAMES", "price": 40}, by=self.user
        )
        self.assertEqual(service.price, 40)
        self.assertEqual(service.price_history.count(), 1)
        self.assertEqual(service.price_history.first().price, 40)

    def test_create_requires_name(self):
        with self.assertRaisesMessage(ValueError, "name is required"):
            ServiceService.create_service(data={"name": "  ", "price": 10}, by=self.user)

    def test_create_requires_positive_price(self):
        with self.assertRaisesMessage(ValueError, "Price must be greater than zero"):
            ServiceService.create_service(data={"name": "Gaming", "price": 0}, by=self.user)

    def test_create_rejects_duplicate_name(self):
        ServiceService.create_service(data={"name": "Gaming", "price": 40}, by=self.user)
        with self.assertRaisesMessage(ValueError, "already exists"):
            ServiceService.create_service(data={"name": "gaming", "price": 50}, by=self.user)

    def test_price_change_appends_history(self):
        service = ServiceService.create_service(
            data={"name": "Gaming", "price": 40}, by=self.user
        )
        updated = ServiceService.update_service(service, data={"price": 50}, by=self.user)
        self.assertEqual(updated.price, 50)
        self.assertEqual(updated.price_history.count(), 2)
        self.assertEqual(updated.price_history.first().price, 50)

    def test_update_without_price_change_no_history(self):
        service = ServiceService.create_service(
            data={"name": "Gaming", "price": 40}, by=self.user
        )
        ServiceService.update_service(service, data={"description": "New desc"}, by=self.user)
        self.assertEqual(service.price_history.count(), 1)

    def test_deactivate_and_restore(self):
        service = ServiceService.create_service(data={"name": "Printing", "price": 5}, by=self.user)
        ServiceService.deactivate_service(service, by=self.user)
        self.assertFalse(Service.objects.filter(pk=service.pk).exists())
        self.assertTrue(Service.all_objects.filter(pk=service.pk).exists())
        ServiceService.restore_service(service, by=self.user)
        self.assertTrue(Service.objects.filter(pk=service.pk).exists())

    def test_price_history_uses_service_relationship(self):
        service = ServiceService.create_service(data={"name": "WiFi", "price": 10}, by=self.user)
        self.assertEqual(ServicePriceHistory.objects.filter(service=service).count(), 1)
