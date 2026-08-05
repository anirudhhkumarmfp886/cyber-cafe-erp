"""
ReferenceService — mints unique, gapless reference numbers for every
financial record (wallets, cash book, bank ledger).

Numbers look like ``WAL-000123`` / ``CB-000045`` / ``BANK-000002``.
Uniqueness and ordering are guaranteed by the Sequence row lock; the caller
is responsible for running inside a transaction when the number must not be
"wasted" on a failed insert.
"""
from django.db import transaction

from apps.common.models import Sequence


class ReferenceService:
    #: Sequence names, kept in one place so prefixes stay consistent.
    WALLET = "WAL"
    CASH_BOOK = "CB"
    BANK = "BANK"
    INVOICE = "INV"
    CASH_OUT = "COUT"

    @staticmethod
    def next(sequence_name: str, digits: int = 6) -> str:
        with transaction.atomic():
            value = Sequence.next(sequence_name)
        return f"{sequence_name}-{value:0{digits}d}"
