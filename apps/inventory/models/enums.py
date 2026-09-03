"""Enums for the inventory app."""
from django.db import models


class UnitType(models.TextChoices):
    PIECE = "PIECE", "Piece"
    PACK = "PACK", "Pack"
    REAM = "REAM", "Ream"
    BOX = "BOX", "Box"
    KG = "KG", "Kilogram"
    LITRE = "LITRE", "Litre"
    METRE = "METRE", "Metre"
    OTHER = "OTHER", "Other"


class MovementType(models.TextChoices):
    PURCHASE = "PURCHASE", "Purchase (Stock In)"
    ISSUE = "ISSUE", "Issued (Stock Out)"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    DAMAGE = "DAMAGE", "Damaged / Wasted"
    RETURN = "RETURN", "Return to Supplier"


#: Movement types that increase stock.
INBOUND_TYPES = {MovementType.PURCHASE}

#: Movement types that decrease stock.
OUTBOUND_TYPES = {MovementType.ISSUE, MovementType.DAMAGE, MovementType.RETURN}
