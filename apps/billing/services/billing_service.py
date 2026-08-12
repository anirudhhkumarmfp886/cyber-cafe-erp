"""
BillingService + CashOutService — the only place invoices and cash-outs move.

Rules enforced here (and nowhere else in the web layer):

  * invoice totals are always derived from lines (qty x snapshot price)
  * a bill can be paid by a split of modes (cash / UPI / card / bank); each
    payment books its own ledger atomically with the invoice and is linked so
    a void can reverse it
  * a cash payment books Cash Book income and credits the billing staff's
    CASH wallet; a bank / UPI payment deposits into the chosen shop bank
    account and credits the staff's ONLINE wallet
  * a credit bill requires a customer and must respect the credit limit; a
    partial payment also requires a customer to track the balance
  * a ``BANK_TRANSFER`` + ``BANK_ACCOUNT`` custom-field pair on a line turns
    the line into a cash-withdrawal: the customer pays the transfer amount,
    the staff hands out cash (from the staff CASH wallet), the commission is
    booked as Cash Book income and the cash given as a Cash Book expense
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
from apps.employees.models import WalletTransactionCategory, WalletType
from apps.employees.services.wallet_service import WalletService
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
    def create_invoice(*, data: dict, lines: list, payments: list = None, by=None) -> Invoice:
        """Create an invoice from header data + lines.

        Each line is ``(Service, qty)`` or ``{"service": S, "qty": Q, "custom": {...}}``
        where ``custom`` maps custom-field PKs to submitted values. Values are
        validated against the service's field definitions and the billing
        user's role, then snapshotted onto the invoice line.

        ``payments`` is an optional list of ``{"mode", "amount", "bank_account"}``
        dicts; when omitted the header ``payment_mode`` is used as a single
        full payment. Cash payments book Cash Book income + a staff CASH
        wallet credit; bank / UPI payments deposit into the chosen shop bank
        account + a staff ONLINE wallet credit. The bank account can also
        come from a withdrawal line on the same bill.

        A paired ``BANK_TRANSFER`` + ``BANK_ACCOUNT`` set on a line turns it
        into a cash-withdrawal line: its amount becomes the transfer value
        (withdrawal + commission), the staff hands the customer cash out of
        the CASH wallet, commission income and the cash-out expense are
        booked, and the transfer is covered by the bill's bank payments.
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
            field_values, withdrawal = BillingService._resolve_custom_fields(service, custom, by)
            if withdrawal is not None:
                amount = _round(Decimal(str(qty)) * withdrawal["transfer"])
            else:
                amount = _round(Decimal(str(qty)) * Decimal(str(service.price)))
            prepared.append((service, qty, amount, field_values, withdrawal))

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
        customer_name = customer.full_name if customer else str(data.get("customer_name") or "").strip()
        party_name = customer_name or "Walk-in Customer"

        if not payments:
            if payment_mode == InvoicePaymentMode.CREDIT:
                payments = []
            else:
                payments = [{"mode": payment_mode, "amount": total, "bank_account": None}]

        cleaned_payments = []
        for raw in payments:
            mode = raw.get("mode")
            amount = _round(raw.get("amount") or 0)
            if amount <= 0 or mode == InvoicePaymentMode.CREDIT:
                continue
            cleaned_payments.append({"mode": mode, "amount": amount, "bank_account": raw.get("bank_account")})

        paid_total = sum(p["amount"] for p in cleaned_payments)
        if paid_total > total:
            raise ValueError(f"Payments sum to {paid_total} which exceeds the bill total of {total}.")
        if paid_total == 0:
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
        elif paid_total < total:
            if customer is None:
                raise ValueError("A partial payment requires a customer to track the balance.")
            limit = Decimal(str(customer.credit_limit or 0))
            if limit > 0:
                outstanding = InvoiceSelector.outstanding_for_customer(customer) + (total - paid_total)
                if outstanding > limit:
                    raise ValueError(
                        f"Credit limit exceeded: outstanding would be {outstanding} against a "
                        f"limit of {limit}."
                    )
            status = InvoiceStatus.PARTIAL
        else:
            status = InvoiceStatus.PAID

        staff = getattr(by, "employee", None)

        with transaction.atomic():
            invoice = Invoice.objects.create(
                invoice_number=ReferenceService.next(ReferenceService.INVOICE),
                customer=customer,
                customer_name=customer_name,
                payment_mode=payment_mode,
                status=status,
                subtotal=subtotal,
                discount=discount,
                total=total,
                notes=data.get("notes", ""),
                created_by=by,
                updated_by=by,
            )

            withdrawal_default_bank = None
            for service, qty, amount, field_values, withdrawal in prepared:
                line = InvoiceLine.objects.create(
                    invoice=invoice,
                    service=service,
                    description=service.name,
                    qty=qty,
                    unit_price=withdrawal["transfer"] if withdrawal is not None else service.price,
                    amount=amount,
                    created_by=by,
                    updated_by=by,
                )
                BillingService._store_field_values(line, field_values, by)
                if withdrawal is not None:
                    if withdrawal_default_bank is None:
                        withdrawal_default_bank = withdrawal["bank_account"]
                    BillingService._book_withdrawal(invoice, withdrawal, party_name, staff, by)

            first_cash_entry = None
            for payment in cleaned_payments:
                mode = payment["mode"]
                amount = payment["amount"]
                if mode == InvoicePaymentMode.CASH:
                    entry = CashBookService.record_income(
                        amount=amount,
                        category=CashEntryCategory.SALES,
                        payment_mode="CASH",
                        party_name=party_name,
                        description=f"Invoice {invoice.invoice_number} cash payment",
                        by=by,
                        staff=staff,
                    )
                    if first_cash_entry is None:
                        first_cash_entry = entry
                    if staff is not None:
                        WalletService.credit(
                            wallet=WalletService.get_or_create_wallet(staff, WalletType.CASH),
                            amount=amount,
                            category=WalletTransactionCategory.PAYMENT_COLLECTED,
                            description=f"Cash collected for {invoice.invoice_number}",
                            source=party_name,
                            destination=staff.full_name,
                            by=by,
                        )
                    InvoicePayment.objects.create(
                        invoice=invoice,
                        amount=amount,
                        payment_mode="CASH",
                        cash_entry=entry,
                        created_by=by,
                        updated_by=by,
                    )
                else:
                    bank_account = payment["bank_account"] or withdrawal_default_bank
                    if bank_account is None:
                        raise ValueError("UPI / bank payments need a shop bank account.")
                    bank_account = BankAccount.objects.select_for_update().get(pk=bank_account.pk)
                    bank_txn = BankService.deposit(
                        account=bank_account,
                        amount=amount,
                        category=BankTransactionCategory.PAYMENT_RECEIVED,
                        party_name=party_name,
                        description=f"Invoice {invoice.invoice_number} {mode} payment",
                        by=by,
                    )
                    if staff is not None:
                        WalletService.credit(
                            wallet=WalletService.get_or_create_wallet(staff, WalletType.ONLINE),
                            amount=amount,
                            category=WalletTransactionCategory.PAYMENT_COLLECTED,
                            description=f"UPI / bank payment for {invoice.invoice_number}",
                            source=party_name,
                            destination=staff.full_name,
                            by=by,
                        )
                    InvoicePayment.objects.create(
                        invoice=invoice,
                        amount=amount,
                        payment_mode=mode,
                        bank_account=bank_account,
                        bank_transaction=bank_txn,
                        created_by=by,
                        updated_by=by,
                    )

            if first_cash_entry is not None:
                invoice.cash_entry = first_cash_entry
                invoice.save(update_fields=["cash_entry", "updated_at"])
            return invoice

    @staticmethod
    def _book_withdrawal(invoice: Invoice, withdrawal: dict, party_name: str, staff, by=None) -> None:
        """Book the cash-out side of a cash-withdrawal line.

        The customer pays the transfer amount (as a bank / UPI payment on the
        same bill); the staff hands out the cash portion from the CASH wallet,
        commission income is booked, and the cash given is booked as a Cash
        Book expense. The bank side is covered by the bill's payments.
        """
        percent = withdrawal["percent"]
        commission = withdrawal["commission"]
        cash_given = withdrawal["cash_given"]
        reference = invoice.invoice_number

        if staff is not None:
            WalletService.debit(
                wallet=WalletService.get_or_create_wallet(staff, WalletType.CASH),
                amount=cash_given,
                category=WalletTransactionCategory.CASH_GIVEN,
                description=f"Cash handed to customer ({reference})",
                source=staff.full_name,
                destination=party_name,
                by=by,
            )
        if commission > 0:
            CashBookService.record_income(
                amount=commission,
                category=CashEntryCategory.COMMISSION,
                payment_mode="BANK_TRANSFER",
                party_name=party_name,
                description=f"Withdrawal commission @ {percent}% ({reference})",
                by=by,
            )
        CashBookService.record_expense(
            amount=cash_given,
            category=CashEntryCategory.CASH_OUT,
            payment_mode="CASH",
            party_name=party_name,
            description=f"Cash given to customer ({reference})",
            by=by,
            staff=staff,
        )
    @staticmethod
    def _resolve_custom_fields(service, custom_data, by):
        """Validate submitted custom-field values for the billing user's role.

        Returns ``(field_values, withdrawal)`` where ``field_values`` is a
        list of ``(field, value_text, bank_account)`` tuples and ``withdrawal``
        is a dict ``{transfer, percent, commission, cash_given, bank_account}``
        when a bank-transfer pair is present (a cash-withdrawal line).
        """
        custom_data = custom_data or {}
        field_values = []
        transfer_amount = None
        percent_value = None
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
                    percent_value = percent
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

        withdrawal = None
        if transfer_amount is not None:
            if bank_account is None:
                raise ValueError(
                    f"'{service.name}' needs a bank account field to deposit the transfer."
                )
            percent = percent_value or Decimal("0")
            cash_given = _round(transfer_amount * Decimal("100") / (Decimal("100") + percent))
            commission = _round(transfer_amount - cash_given)
            if commission < 0:
                raise ValueError("Commission cannot exceed the transfer amount.")
            withdrawal = {
                "percent": percent,
                "transfer": transfer_amount,
                "commission": commission,
                "cash_given": cash_given,
                "bank_account": bank_account,
            }
        return field_values, withdrawal

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
        """Void an invoice: soft-delete it and reverse its ledger entries."""
        entries = [invoice.cash_entry]
        bank_txns = []
        for payment in invoice.payments.all():
            if payment.cash_entry is not None:
                entries.append(payment.cash_entry)
            if payment.bank_transaction is not None:
                bank_txns.append(payment.bank_transaction)
        invoice.soft_delete(by=by)
        for entry in entries:
            if entry is not None and entry.is_active:
                entry.soft_delete(by=by)
        for txn in bank_txns:
            if txn is not None and txn.is_active:
                txn.soft_delete(by=by)
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
