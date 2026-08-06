"""Admin configuration for the service catalog."""
from django.contrib import admin

from apps.common.admin import BaseAdmin
from apps.services.models import Category, Service, ServiceCustomField, ServicePriceHistory


@admin.register(Category)
class CategoryAdmin(BaseAdmin):
    list_display = ("name", "is_active", "created_at")
    search_fields = ("name",)


@admin.register(Service)
class ServiceAdmin(BaseAdmin):
    list_display = ("name", "category", "unit", "price", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")


@admin.register(ServiceCustomField)
class ServiceCustomFieldAdmin(BaseAdmin):
    list_display = ("service", "label", "field_type", "required", "ordering", "is_active")
    list_filter = ("field_type", "required", "is_active")
    search_fields = ("service__name", "label")


@admin.register(ServicePriceHistory)
class ServicePriceHistoryAdmin(BaseAdmin):
    list_display = ("service", "price", "effective_from", "notes", "created_at")
    list_filter = ("effective_from",)
    search_fields = ("service__name", "notes")
    autocomplete_fields = ("service",)
