"""Work Entry application configuration."""
from django.apps import AppConfig


class WorkentryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workentry"
    verbose_name = "Work Entry"
