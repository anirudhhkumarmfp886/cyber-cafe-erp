"""Shared template tags for the ERP (currency, display helpers)."""
from decimal import Decimal, ROUND_HALF_UP

from django import template
from django.conf import settings
from django.utils.formats import number_format

register = template.Library()


@register.filter(name="inr")
def inr(value, decimal_places: int = 2) -> str:
    """Render a number as an Indian Rupee amount: 12345.6 -> \u20b91,23,45.60.

    Safe on None, empty strings and non-numeric values.
    """
    if value in (None, ""):
        return "\u20b90.00"
    try:
        amount = Decimal(str(value))
    except Exception:
        return str(value)
    amount = amount.quantize(Decimal("1." + "0" * decimal_places), rounding=ROUND_HALF_UP)
    formatted = number_format(amount, decimal_pos=decimal_places, use_l10n=True)
    return f"\u20b9{formatted}"


@register.filter(name="active_choices")
def active_choices(value, choices):
    """Return the human label for a model TextChoices value."""
    if value in (None, ""):
        return "—"
    for choice_value, label in choices:
        if choice_value == value:
            return label
    return value


@register.filter(name="add_class")
def add_class(field, css_class: str):
    """Render a form field with an extra CSS class (e.g. Bootstrap form-control)."""
    return field.as_widget(attrs={"class": css_class})


@register.simple_tag
def money_decimal_places() -> int:
    return settings.MONEY_DECIMAL_PLACES
