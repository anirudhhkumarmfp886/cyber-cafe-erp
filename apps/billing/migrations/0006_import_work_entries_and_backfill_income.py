"""
Sprint 4.5 data migration.

1. Backfill ``InvoiceLine.income_amount`` for every existing line. All
   pre-4.5 lines were plain sales (withdrawal semantics were recorded as
   line field values, but the line amount itself was shop income), so
   ``income_amount = amount`` preserves historical P&L.

2. Import every SAVED ``WorkEntry`` into an ``Invoice`` + ``InvoiceLine``
   (copy-only — the original ledger entries booked by WorkEntryService are
   untouched, so nothing is re-booked and the cash book stays truthful).
   DRAFT entries never moved money and are left alone.

The WorkEntry counter surface is retired in the same sprint; the invoices
created here become the authoritative record of that business.
"""
from decimal import Decimal

from django.db import migrations, transaction

#: Map a WorkPaymentMode to the equivalent InvoicePaymentMode.
PAYMENT_MODE_MAP = {
    "CASH": "CASH",
    "UPI": "UPI",
    "CARD": "CARD",
    "BANK_TRANSFER": "BANK_TRANSFER",
    "CUSTOMER_CREDIT": "CUSTOMER_WALLET",
}


def _money(value) -> Decimal:
    return Decimal(str(value or 0))


def backfill_income_amounts(apps, schema_editor):
    InvoiceLine = apps.get_model("billing", "InvoiceLine")
    updated = 0
    for line in InvoiceLine.objects.only("id", "amount"):
        if line.income_amount != line.amount:
            line.income_amount = line.amount
            line.save(update_fields=["income_amount", "updated_at"])
            updated += 1
    if updated:
        print(f"  Backfilled income_amount on {updated} invoice line(s).")


def import_work_entries(apps, schema_editor):
    Invoice = apps.get_model("billing", "Invoice")
    InvoiceLine = apps.get_model("billing", "InvoiceLine")
    InvoiceLineFieldValue = apps.get_model("billing", "InvoiceLineFieldValue")
    InvoicePayment = apps.get_model("billing", "InvoicePayment")
    WorkEntry = apps.get_model("workentry", "WorkEntry")
    Sequence = apps.get_model("common", "Sequence")

    entries = WorkEntry.objects.filter(status="SAVED").order_by("created_at")
    created = 0
    for entry in entries.iterator():
        with transaction.atomic():
            # Mint the next INV-xxxxxx (mirrors ReferenceService.next).
            seq, _ = Sequence.objects.select_for_update().get_or_create(name="INV")
            seq.last_value += 1
            seq.save(update_fields=["last_value", "updated_at"])
            invoice_number = f"INV-{seq.last_value:06d}"

            if entry.customer_id is None and not entry.customer_name:
                customer_name = "Walk-in Customer"
            else:
                customer_name = entry.customer_name or (
                    entry.customer.full_name if entry.customer else "Walk-in Customer"
                )

            qty = entry.page_quantity if entry.page_quantity and entry.page_quantity > 0 else Decimal("1")
            charged = _money(entry.charged_amount)
            if charged > 0:
                unit_price = (charged / qty).quantize(Decimal("0.01"))
            else:
                unit_price = Decimal("0")

            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                customer_id=entry.customer_id,
                customer_name=customer_name,
                payment_mode=PAYMENT_MODE_MAP.get(entry.payment_mode, "CASH"),
                status="PAID",
                subtotal=_money(entry.total),
                discount=Decimal("0"),
                total=_money(entry.total),
                notes=entry.notes,
                billed_on=entry.entry_date,
                related_reference=entry.reference_number,
                created_by_id=entry.updated_by_id,
                updated_by_id=entry.updated_by_id,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )

            line = InvoiceLine.objects.create(
                invoice=invoice,
                service_id=entry.service_id,
                description=entry.service.name,
                qty=qty,
                unit_price=unit_price,
                amount=_money(entry.total),
                income_amount=charged,
                created_by_id=entry.updated_by_id,
                updated_by_id=entry.updated_by_id,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )

            legs = [
                ("Charged Amount", charged),
                ("Transfer to Customer", _money(entry.transfer_to_customer)),
                ("Transfer on Behalf", _money(entry.transfer_on_behalf)),
                ("Cash Withdrawal", _money(entry.cash_withdrawal)),
                ("Customer Credit Used", _money(entry.credit_used)),
            ]
            for label, value in legs:
                if value > 0:
                    InvoiceLineFieldValue.objects.create(
                        line=line,
                        field=None,
                        field_label=label,
                        field_type="NUMBER",
                        value_text=str(value),
                        created_by_id=entry.updated_by_id,
                        updated_by_id=entry.updated_by_id,
                        created_at=entry.created_at,
                        updated_at=entry.updated_at,
                    )

            payment_mode = PAYMENT_MODE_MAP.get(entry.payment_mode, "CASH")
            notes = f"Imported from {entry.reference_number}"
            if entry.credit_used and entry.credit_used > 0:
                notes += (
                    f" (customer credit {entry.credit_used}; rest paid via "
                    f"{entry.credit_rest_mode or 'CASH'})"
                )
            InvoicePayment.objects.create(
                invoice=invoice,
                amount=_money(entry.total),
                payment_mode=payment_mode,
                payment_date=entry.entry_date,
                notes=notes,
                created_by_id=entry.updated_by_id,
                updated_by_id=entry.updated_by_id,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
            created += 1
    if created:
        print(f"  Imported {created} work entrie(s) as invoices.")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_invoice_related_reference_and_more"),
        ("workentry", "0001_initial"),
        ("common", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_income_amounts, migrations.RunPython.noop),
        migrations.RunPython(import_work_entries, migrations.RunPython.noop),
    ]
