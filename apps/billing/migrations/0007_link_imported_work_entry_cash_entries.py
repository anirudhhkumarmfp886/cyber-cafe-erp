"""
Sprint 4.5 follow-up data migration.

``0006`` imported SAVED WorkEntries as invoices but left the original
``CashBookService.record_income`` SALES entries created by WorkEntryService
unlinked. With the P&L now reading ``InvoiceLine.income_amount`` as its
authoritative income source and excluding invoice-linked cash entries, those
orphaned entries would be double-counted. Link each imported invoice's
payment to its original work-entry cash entry so the ledger stays truthful.
"""
from django.db import migrations, transaction


def link_imported_work_entry_cash_entries(apps, schema_editor):
    Invoice = apps.get_model("billing", "Invoice")
    InvoicePayment = apps.get_model("billing", "InvoicePayment")
    CashBookEntry = apps.get_model("finance", "CashBookEntry")

    linked = 0
    for invoice in Invoice.objects.filter(related_reference__startswith="WE-").iterator():
        with transaction.atomic():
            original = (
                CashBookEntry.objects.filter(
                    entry_type="INCOME",
                    description__startswith=f"Work entry {invoice.related_reference} ",
                )
                .order_by("created_at")
                .first()
            )
            if original is None:
                continue
            if invoice.cash_entry_id is None:
                invoice.cash_entry = original
                invoice.save(update_fields=["cash_entry", "updated_at"])
            InvoicePayment.objects.filter(invoice=invoice, cash_entry_id__isnull=True).update(
                cash_entry=original
            )
            linked += 1
    if linked:
        print(f"  Linked {linked} imported work entry invoice(s) to their cash entries.")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_import_work_entries_and_backfill_income"),
    ]

    operations = [
        migrations.RunPython(link_imported_work_entry_cash_entries, migrations.RunPython.noop),
    ]
