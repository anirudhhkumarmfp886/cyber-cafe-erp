"""Admin configuration for the service catalog."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.services.models import Service, ServicePriceHistory


@admin.register(Service)
class ServiceAdmin(BaseAdmin):
    list_display = ("name", "category", "unit", "price", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")


@admin.register(ServicePriceHistory)
class ServicePriceHistoryAdmin(BaseAdmin):
    list_display = ("service", "price", "effective_from", "notes", "created_at")
    list_filter = ("effective_from",)
    search_fields = ("service__name", "notes")
    autocomplete_fields = ("service",)
