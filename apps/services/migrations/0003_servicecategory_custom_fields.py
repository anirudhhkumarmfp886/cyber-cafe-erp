import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_DEFAULT_CATEGORIES = ["Games", "Internet", "Printing", "Recharge", "Snacks", "Other"]

_OLD_TO_NAME = {
    "GAMES": "Games",
    "INTERNET": "Internet",
    "PRINTING": "Printing",
    "RECHARGE": "Recharge",
    "SNACKS": "Snacks",
    "OTHER": "Other",
}


def _seed_categories(apps, schema_editor):
    """Create the default categories and map every service onto one."""
    Category = apps.get_model("services", "Category")
    Service = apps.get_model("services", "Service")
    by_name = {name: Category.objects.create(name=name) for name in _DEFAULT_CATEGORIES}
    other = by_name["Other"]
    for service in Service.objects.all():
        target = by_name.get(_OLD_TO_NAME.get(service.category, ""), other)
        service.category_new = target
        service.save(update_fields=["category_new"])


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0002_alter_service_category"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, editable=False, null=True)),
                ("name", models.CharField(max_length=50, unique=True)),
                ("created_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("deleted_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Service Category",
                "verbose_name_plural": "Service Categories",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ServiceCustomField",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, editable=False, null=True)),
                ("label", models.CharField(max_length=100)),
                ("field_type", models.CharField(choices=[("TEXT", "Text"), ("NUMBER", "Number (amount)"), ("PERCENT", "Percentage"), ("DATE", "Date"), ("BANK_ACCOUNT", "Bank Account"), ("BANK_TRANSFER", "Bank Transfer (auto-deposit)")], db_index=True, default="TEXT", max_length=20)),
                ("required", models.BooleanField(default=False)),
                ("help_text", models.CharField(blank=True, max_length=200)),
                ("roles", models.CharField(blank=True, help_text="Comma-separated role codes allowed to fill this field. Leave blank for all billing staff.", max_length=200)),
                ("ordering", models.PositiveIntegerField(default=0)),
                ("created_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("deleted_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="custom_fields", to="services.service")),
                ("updated_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Service Custom Field",
                "verbose_name_plural": "Service Custom Fields",
                "ordering": ["ordering", "created_at"],
            },
        ),
        migrations.AddField(
            model_name="service",
            name="category_new",
            field=models.ForeignKey(blank=True, help_text="Optional; defaults to the 'Other' category.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="services", to="services.category"),
        ),
        migrations.RunPython(_seed_categories, _noop),
        migrations.RemoveIndex(
            model_name="service",
            name="services_se_categor_dc5d11_idx",
        ),
        migrations.RemoveField(
            model_name="service",
            name="category",
        ),
        migrations.RenameField(
            model_name="service",
            old_name="category_new",
            new_name="category",
        ),
        migrations.AlterModelOptions(
            name="service",
            options={"ordering": ["category__name", "name"], "verbose_name": "Service", "verbose_name_plural": "Services"},
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["category", "name"], name="services_se_categor_fd84b9_idx"),
        ),
        migrations.AddIndex(
            model_name="servicecustomfield",
            index=models.Index(fields=["service", "field_type"], name="services_se_service_24ad7e_idx"),
        ),
    ]
