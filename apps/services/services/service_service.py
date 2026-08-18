"""
ServiceService — the only place services and their price history change.

Creating a service also records the opening price. Editing the price is
append-only: the current price moves, and a ServicePriceHistory row is
added so every past bill can be explained.

Categories are free-form: the owner can pick an existing ``Category`` or
type a new one (the legacy choice codes GAMES / INTERNET / ... are mapped
onto their seeded display names for backwards compatibility). Custom fields
are owner-managed dynamic inputs captured on the bill for a service.

Pricing formulas (``total_formula`` / ``income_formula``) and the
``passthrough_type`` are validated here so the billing engine only ever
sees syntactically valid, fully-resolved expressions. A field's
``variable_name`` is auto-derived from its label when left blank and kept
unique within the service.
"""
from datetime import date

from apps.common.services.formula import (
    FormulaError,
    ServicePassThroughType,
    slugify_variable,
    validate,
    validate_for_names,
)
from apps.services.models import (
    Category,
    CustomFieldType,
    Service,
    ServiceCustomField,
    ServicePriceHistory,
)

_EDITABLE_FIELDS = (
    "name",
    "unit",
    "price",
    "description",
    "passthrough_type",
    "total_formula",
    "income_formula",
)

_LEGACY_CATEGORIES = {
    "GAMES": "Games",
    "INTERNET": "Internet",
    "PRINTING": "Printing",
    "RECHARGE": "Recharge",
    "SNACKS": "Snacks",
    "OTHER": "Other",
}


def _normalize_category_name(name: str) -> str:
    name = name.strip()
    if name.upper() in _LEGACY_CATEGORIES:
        return _LEGACY_CATEGORIES[name.upper()]
    return name


def _resolve_category(data: dict):
    """Return a Category from ``new_category`` / ``category`` / default."""
    new_name = str(data.get("new_category") or "").strip()
    if new_name:
        return Category.objects.get_or_create(name=_normalize_category_name(new_name))[0]

    category = data.get("category")
    if isinstance(category, Category):
        return category
    name = str(category or "").strip()
    if not name:
        return Category.objects.get_or_create(name="Other")[0]
    return Category.objects.get_or_create(name=_normalize_category_name(name))[0]


def _clean_formulas(
    data: dict, *, service: Service | None = None, field_names: set, resolve_names: bool = True
) -> dict:
    """Validate and return normalized pricing formulas.

    Every referenced variable must resolve to a field on the service (or the
    always-available ``qty`` / ``price``). When ``resolve_names`` is False
    (creating a service before its fields exist) only syntax is checked —
    the owner adds custom fields afterwards and the next save resolves names.
    An income formula is only allowed when the service is a pass-through
    type other than NONE.
    """
    total_formula = str(data.get("total_formula") or "").strip()
    income_formula = str(data.get("income_formula") or "").strip()
    passthrough_type = data.get("passthrough_type") or ServicePassThroughType.NONE

    if total_formula:
        try:
            validate(total_formula)
        except FormulaError as exc:
            raise ValueError(f"Total formula is invalid: {exc}") from exc
        if resolve_names:
            unknown = validate_for_names(total_formula, field_names)
            if unknown:
                raise ValueError(
                    f"Total formula references unknown variable(s): {', '.join(sorted(unknown))}. "
                    "They must match a custom-field variable name, or qty/price."
                )

    if income_formula:
        if passthrough_type == ServicePassThroughType.NONE:
            raise ValueError(
                "An income formula requires a pass-through type (cash or online); "
                "a plain sale keeps the whole line as income."
            )
        try:
            validate(income_formula)
        except FormulaError as exc:
            raise ValueError(f"Income formula is invalid: {exc}") from exc
        if resolve_names:
            unknown = validate_for_names(income_formula, field_names)
            if unknown:
                raise ValueError(
                    f"Income formula references unknown variable(s): {', '.join(sorted(unknown))}. "
                    "They must match a custom-field variable name, or qty/price."
                )
    else:
        income_formula = ""

    return {
        "passthrough_type": passthrough_type,
        "total_formula": total_formula,
        "income_formula": income_formula,
    }


def _field_variable_names(service: Service) -> set:
    names = {"qty", "price"}
    if service is not None:
        names.update(service.custom_fields.values_list("variable_name", flat=True))
    return names


class ServiceService:
    @staticmethod
    def create_service(*, data: dict, by=None, effective_from=None) -> Service:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Service name is required.")

        price = data.get("price")
        if price is None or price <= 0:
            raise ValueError("Price must be greater than zero.")

        if Service.objects.filter(name__iexact=name).exists():
            raise ValueError("A service with this name already exists.")

        formulas = _clean_formulas(
            data, service=None, field_names={"qty", "price"}, resolve_names=False
        )

        effective_from = effective_from or date.today()
        service = Service.objects.create(
            name=name,
            category=_resolve_category(data),
            unit=data.get("unit", ""),
            price=price,
            description=data.get("description", ""),
            passthrough_type=formulas["passthrough_type"],
            total_formula=formulas["total_formula"],
            income_formula=formulas["income_formula"],
            created_by=by,
            updated_by=by,
        )
        ServicePriceHistory.objects.create(
            service=service,
            price=price,
            effective_from=effective_from,
            notes="Initial price",
            created_by=by,
            updated_by=by,
        )
        return service

    @staticmethod
    def update_service(service: Service, *, data: dict, by=None, effective_from=None) -> Service:
        data = dict(data or {})
        if "total_formula" not in data or "income_formula" not in data:
            data["total_formula"] = service.total_formula
            data["income_formula"] = service.income_formula
        if "passthrough_type" not in data:
            data["passthrough_type"] = service.passthrough_type

        formulas = _clean_formulas(data, service=service, field_names=_field_variable_names(service))
        data.update(formulas)

        for field in _EDITABLE_FIELDS:
            if field in data:
                setattr(service, field, data[field])

        new_category = data.get("new_category")
        category = data.get("category")
        if new_category or category:
            service.category = _resolve_category(data)

        new_price = service.price
        if new_price is None or new_price <= 0:
            raise ValueError("Price must be greater than zero.")

        price_changed = (
            not service.price_history.exists() or service.price_history.first().price != new_price
        )
        service.updated_by = by
        service.save()

        if price_changed:
            ServicePriceHistory.objects.create(
                service=service,
                price=new_price,
                effective_from=effective_from or date.today(),
                notes="Price updated",
                created_by=by,
                updated_by=by,
            )
        return service

    @staticmethod
    def deactivate_service(service: Service, *, by=None) -> Service:
        return service.soft_delete(by=by)

    @staticmethod
    def restore_service(service: Service, *, by=None) -> Service:
        return service.restore(by=by)

    @staticmethod
    def create_custom_field(service: Service, *, data: dict, by=None) -> ServiceCustomField:
        label = str(data.get("label", "")).strip()
        if not label:
            raise ValueError("Field label is required.")

        variable_name = str(data.get("variable_name") or "").strip()
        if not variable_name:
            variable_name = slugify_variable(label)
        if not variable_name.isidentifier():
            raise ValueError(
                f"Variable name '{variable_name}' is not a valid identifier. "
                "Use letters, digits and underscores only."
            )
        if service.custom_fields.filter(variable_name=variable_name).exists():
            raise ValueError(f"A field with variable name '{variable_name}' already exists.")

        roles = [code for code in data.get("roles", []) if code]
        return ServiceCustomField.objects.create(
            service=service,
            label=label,
            variable_name=variable_name,
            field_type=data.get("field_type") or CustomFieldType.TEXT,
            required=bool(data.get("required")),
            help_text=str(data.get("help_text", "")).strip(),
            roles=",".join(roles),
            ordering=int(data.get("ordering") or 0),
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    def update_custom_field(field: ServiceCustomField, *, data: dict, by=None) -> ServiceCustomField:
        variable_name = str(data.get("variable_name") or "").strip()
        if variable_name:
            if not variable_name.isidentifier():
                raise ValueError(
                    f"Variable name '{variable_name}' is not a valid identifier. "
                    "Use letters, digits and underscores only."
                )
            duplicate = field.service.custom_fields.exclude(pk=field.pk).filter(
                variable_name=variable_name
            )
            if duplicate.exists():
                raise ValueError(f"A field with variable name '{variable_name}' already exists.")
            field.variable_name = variable_name

        label = str(data.get("label") or "").strip()
        if label:
            field.label = label
        field.field_type = data.get("field_type") or field.field_type
        field.required = bool(data.get("required"))
        field.help_text = str(data.get("help_text", "")).strip()
        field.roles = ",".join(code for code in data.get("roles", []) if code)
        if "ordering" in data and data["ordering"] is not None:
            field.ordering = int(data["ordering"])
        field.updated_by = by
        field.save()
        return field

    @staticmethod
    def delete_custom_field(field: ServiceCustomField, *, by=None) -> ServiceCustomField:
        return field.soft_delete(by=by)
