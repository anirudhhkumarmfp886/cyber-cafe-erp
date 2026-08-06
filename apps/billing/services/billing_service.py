"""
BillingService + CashOutService — the only place invoices and cash-outs move.

Rules enforced here (and nowhere else in the web layer):

  * invoice totals are always derived from lines (qty x snapshot price)
  * a bill paid by cash / UPI / card / bank transfer records its income in
    the Cash Book atomically; the entry is linked so a void can reverse it
  * a credit bill requires a customer and must respect the credit limit
  * settlements only move toward the outstanding amount; a full settlement
    records Cash Book income and marks the invoice PAID
  * a cash-out deposits the transfer into the bank, pays the customer cash
    (after a manually-entered commission percentage) and books both the
    commission income and the cash-out expense traceably
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from apps.common.services.reference_service import ReferenceService
from apps.billing.models import (
    CashOut,
    Invoice,
    InvoiceLine,
    InvoiceLineFieldValue,
    InvoicePayment,
    InvoicePaymentMode,
    InvoiceStatus,
)
from apps.billing.selectors.invoice_selector import InvoiceSelector
from apps.finance.models import BankAccount
from apps.finance.models.enums import (
    BankTransactionCategory,
    CashEntryCategory,
)
from apps.finance.services.bank_service import BankService
from apps.finance.services.cashbook_service import CashBookService
from apps.services.models import CustomFieldType, ServiceCustomField
from apps.services.selectors.service_selector import ServiceSelector

_MONEY = Decimal("0.01")


def _round(value) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _parse_line(line):
    """Normalise a line into (service, qty, custom) — accepts legacy tuples."""
    if isinstance(line, dict):
        return line["service"], line["qty"], line.get("custom") or {}
    if isinstance(line, (tuple, list)):
        service, qty = line[0], line[1]
        custom = line[2] if len(line) > 2 else {}
        return service, qty, custom
    raise ValueError("Each line must be a (service, qty) tuple or a dict with service/qty/custom.")


class BillingService:
    @staticmethod
    def create_invoice(*, data: dict, lines: list, by=None) -> Invoice:
        """Create an invoice from header data + lines.

        Each line is ``(Service, qty)`` or ``{"service": S, "qty": Q, "custom": {...}}``
        where ``custom`` maps custom-field PKs to submitted values. Values are
        validated against the service's field definitions and the billing
        user's role, then snapshotted onto the invoice line. A paired
        ``BANK_TRANSFER`` + ``BANK_ACCOUNT`` set books a real bank deposit
        into the chosen account atomically with the invoice.
        """
        if not lines:
            raise ValueError("An invoice needs at least one line item.")

        prepared = []
        for raw in lines:
            service, qty, custom = _parse_line(raw)
            if qty is None or qty <= 0:
                raise ValueError("Line quantities must be greater than zero.")
            if not service.is_active:
                raise ValueError(f"Service '{service.name}' is inactive and cannot be billed.")
            amount = _round(Decimal(str(qty)) * Decimal(str(service.price)))
            field_values, deposit = BillingService._resolve_custom_fields(service, custom, by)
            prepared.append((service, qty, amount, field_values, deposit))

        subtotal = Decimal("0")
        for _, _, amount, _, _ in prepared:
            subtotal += amount

        discount = Decimal(str(data.get("discount") or 0))
        if discount < 0:
            raise ValueError("Discount cannot be negative.")
        if discount > subtotal:
            raise ValueError("Discount cannot exceed the bill total.")
        total = _round(subtotal - discount)

        payment_mode = data.get("payment_mode") or InvoicePaymentMode.CASH
        customer = data.get("customer")

        with transaction.atomic():
            if payment_mode == InvoicePaymentMode.CREDIT:
                if customer is None:
                    raise ValueError("Credit billing requires a customer.")
                limit = Decimal(str(customer.credit_limit or 0))
                if limit <= 0:
                    raise ValueError("This customer has no credit limit.")
                outstanding = InvoiceSelector.outstanding_for_customer(customer) + total
                if outstanding > limit:
                    raise ValueError(
                        f"Credit limit exceeded: outstanding would be {outstanding} against a "
                        f"limit of {limit}."
                    )
                status = InvoiceStatus.UNPAID
                cash_entry = None
            else:
                status = InvoiceStatus.PAID
                cash_entry = CashBookService.record_income(
                    amount=total,
                    category=CashEntryCategory.SALES,
                    payment_mode=payment_mode,
                    party_name=customer.full_name if customer else "Walk-in Customer",
                    description=f"Invoice billing (lines: {len(prepared)})",
                    by=by,
                )

            invoice = Invoice.objects.create(
                invoice_number=ReferenceService.next(ReferenceService.INVOICE),
                customer=customer,
                payment_mode=payment_mode,
                status=status,
                subtotal=subtotal,
                discount=discount,
                total=total,
                notes=data.get("notes", ""),
                cash_entry=cash_entry,
                created_by=by,
                updated_by=by,
            )
            for service, qty, amount, field_values, deposit in prepared:
                line = InvoiceLine.objects.create(
                    invoice=invoice,
                    service=service,
                    description=service.name,
                    qty=qty,
                    unit_price=service.price,
                    amount=amount,
                    created_by=by,
                    updated_by=by,
                )
                BillingService._store_field_values(line, field_values, by)
                if deposit is not None:
                    bank_account, transfer_amount = deposit
                    BankService.deposit(
                        account=bank_account,
                        amount=transfer_amount,
                        category=BankTransactionCategory.PAYMENT_RECEIVED,
                        party_name=customer.full_name if customer else "Walk-in Customer",
                        description=(
                            f"{service.name} transfer-in for {invoice.invoice_number}"
                        ),
                        by=by,
                    )
            return invoice

    @staticmethod
    def _resolve_custom_fields(service, custom_data, by):
        """Validate submitted custom-field values for the billing user's role.

        Returns ``(field_values, deposit)`` where ``field_values`` is a list
        of ``(field, value_text, bank_account)`` tuples and ``deposit`` is
        ``(bank_account, amount)`` when a bank-transfer pair is present.
        """
        custom_data = custom_data or {}
        field_values = []
        transfer_amount = None
        bank_account = None
        allowed_fields = ServiceSelector.visible_custom_fields(service, by)
        allowed_keys = {str(f.pk) for f in allowed_fields}

        for field in allowed_fields:
            raw = custom_data.get(str(field.pk))
            value_text = ""
            account = None

            if field.field_type == CustomFieldType.BANK_ACCOUNT:
                if raw:
                    account = BankAccount.objects.filter(id=str(raw)).first()
                    if account is None:
                        raise ValueError(f"Invalid bank account for '{field.label}'.")
                if field.required and account is None:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")
                bank_account = account

            elif field.field_type == CustomFieldType.BANK_TRANSFER:
                if raw:
                    amount = _round(raw)
                    if amount <= 0:
                        raise ValueError(f"'{field.label}' must be greater than zero.")
                    value_text = str(amount)
                    transfer_amount = amount
                if field.required and not raw:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            elif field.field_type == CustomFieldType.PERCENT:
                if raw:
                    percent = Decimal(str(raw))
                    if percent < 0 or percent > 100:
                        raise ValueError(f"'{field.label}' must be between 0 and 100.")
                    value_text = str(percent)
                if field.required and not raw:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            elif field.field_type == CustomFieldType.NUMBER:
                if raw:
                    number = Decimal(str(raw))
                    if number < 0:
                        raise ValueError(f"'{field.label}' cannot be negative.")
                    value_text = str(_round(number))
                if field.required and not raw:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            elif field.field_type == CustomFieldType.DATE:
                if raw:
                    from datetime import datetime

                    try:
                        value_text = datetime.strptime(str(raw), "%Y-%m-%d").date().isoformat()
                    except ValueError:
                        raise ValueError(f"'{field.label}' must be a valid date.")
                if field.required and not raw:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            else:  # TEXT
                value_text = str(raw).strip() if raw else ""
                if field.required and not value_text:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            field_values.append((field, value_text, account))

        submitted_keys = {str(k) for k in (custom_data.keys() or [])}
        for key in submitted_keys:
            if key not in allowed_keys and str(custom_data.get(key) or "").strip():
                field = ServiceCustomField.objects.filter(pk=key).first()
                label = field.label if field else "This field"
                raise ValueError(f"You do not have permission to set '{label}'.")

        deposit = None
        if transfer_amount is not None:
            if bank_account is None:
                raise ValueError(
                    f"'{service.name}' needs a bank account field to deposit the transfer."
                )
            deposit = (bank_account, transfer_amount)
        return field_values, deposit

    @staticmethod
    def _store_field_values(line: InvoiceLine, field_values, by=None) -> None:
        for field, value_text, bank_account in field_values:
            if not value_text and bank_account is None:
                continue
            InvoiceLineFieldValue.objects.create(
                line=line,
                field=field,
                field_label=field.label,
                field_type=field.field_type,
                value_text=value_text,
                bank_account=bank_account,
                created_by=by,
                updated_by=by,
            )

    @staticmethod
    @transaction.atomic
    def settle_invoice(*, invoice: Invoice, amount, payment_mode: str, notes: str = "", by=None) -> InvoicePayment:
        """Record a payment against an unpaid invoice and update its status."""
        if invoice.status == InvoiceStatus.PAID:
            raise ValueError("This invoice is already fully paid.")

        amount = _round(amount)
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        outstanding = invoice.outstanding_amount
        if amount > outstanding:
            raise ValueError(f"Payment exceeds the outstanding amount of {outstanding}.")

        party_name = invoice.customer.full_name if invoice.customer else "Walk-in Customer"
        cash_entry = CashBookService.record_income(
            amount=amount,
            category=CashEntryCategory.SALES,
            payment_mode=payment_mode,
            party_name=party_name,
            description=f"Payment for {invoice.invoice_number}",
            by=by,
        )
        payment = InvoicePayment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_mode=payment_mode,
            cash_entry=cash_entry,
            notes=notes,
            created_by=by,
            updated_by=by,
        )

        if invoice.paid_amount >= invoice.total:
            invoice.status = InvoiceStatus.PAID
        else:
            invoice.status = InvoiceStatus.PARTIAL
        invoice.updated_by = by
        invoice.save(update_fields=["status", "updated_by", "updated_at"])
        return payment

    @staticmethod
    @transaction.atomic
    def soft_delete_invoice(*, invoice: Invoice, by=None) -> Invoice:
        """Void an invoice: soft-delete it and reverse its Cash Book entries."""
        entries = [invoice.cash_entry]
        entries += [p.cash_entry for p in invoice.payments.all()]
        invoice.soft_delete(by=by)
        for entry in entries:
            if entry is not None and entry.is_active:
                entry.soft_delete(by=by)
        return invoice


class CashOutService:
    @staticmethod
    @transaction.atomic
    def create_cash_out(*, data: dict, by=None) -> CashOut:
        """Cash out: bank deposit + commission income + cash paid out."""
        transfer_amount = _round(data.get("transfer_amount") or 0)
        if transfer_amount <= 0:
            raise ValueError("Transfer amount must be greater than zero.")

        percent = Decimal(str(data.get("commission_percent") or 0))
        if percent < 0 or percent > 100:
            raise ValueError("Commission must be between 0 and 100 percent.")

        bank_account = data.get("bank_account")
        if bank_account is None:
            raise ValueError("A bank account is required.")
        bank_account = BankAccount.objects.select_for_update().get(pk=bank_account.pk)

        commission_amount = _round(transfer_amount * percent / Decimal("100"))
        cash_given = _round(transfer_amount - commission_amount)
        if cash_given < 0:
            raise ValueError("Commission cannot exceed the transfer amount.")

        customer = data.get("customer")
        party_name = customer.full_name if customer else "Walk-in Customer"

        reference = ReferenceService.next(ReferenceService.CASH_OUT)
        BankService.deposit(
            account=bank_account,
            amount=transfer_amount,
            category=BankTransactionCategory.PAYMENT_RECEIVED,
            party_name=party_name,
            description=f"Cash out {reference} transfer-in for customer cash",
            by=by,
        )
        if commission_amount > 0:
            CashBookService.record_income(
                amount=commission_amount,
                category=CashEntryCategory.COMMISSION,
                payment_mode="BANK_TRANSFER",
                party_name=party_name,
                description=f"Cash out {reference} commission @ {percent}%",
                by=by,
            )
        CashBookService.record_expense(
            amount=cash_given,
            category=CashEntryCategory.CASH_OUT,
            payment_mode="CASH",
            party_name=party_name,
            description=f"Cash out {reference} cash given to customer",
            by=by,
        )

        return CashOut.objects.create(
            reference_number=reference,
            customer=customer,
            bank_account=bank_account,
            transfer_amount=transfer_amount,
            commission_percent=percent,
            commission_amount=commission_amount,
            cash_given=cash_given,
            notes=data.get("notes", ""),
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    def soft_delete_cash_out(*, cash_out: CashOut, by=None) -> CashOut:
        # Ledger entries stay (a cash-out is irreversible); only the record
        # is hidden. Documented in PROJECT_STATUS.md debt list.
        return cash_out.soft_delete(by=by)
