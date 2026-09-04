"""
BillingService — the only place invoices move money.

Rules enforced here (and nowhere else in the web layer):

  * invoice totals are always derived from lines (qty x snapshot price, or a
    service's pricing formula)
  * a bill can be paid by a split of modes (cash / UPI / card / bank /
    customer wallet); each payment books its own ledger atomically with the
    invoice and is linked so a void can reverse it
  * a cash payment books Cash Book income and credits the billing staff's
    CASH wallet; a bank / UPI payment deposits into the chosen shop bank
    account and credits the staff's ONLINE wallet; a customer-wallet payment
    draws down the customer's pre-paid credit balance (no new cash moves)
  * a credit bill requires a customer and must respect the credit limit; a
    partial payment also requires a customer to track the balance
  * how much a line is charged and how much the shop keeps is formula-driven:
    a service with ``total_formula`` / ``income_formula`` is priced against
    its captured custom-field variables (see apps.common.services.formula).
    The difference between the two is pass-through money the shop executes on
    the customer's behalf:
        CASH   passthrough -> staff CASH wallet debit (cash given out) +
                              cash-out expense + commission income
        ONLINE passthrough -> staff ONLINE wallet debit (money sent onward)
    A service with no formulas is a plain ``qty x price`` sale (income equals
    the full amount). A legacy ``BANK_TRANSFER`` + ``BANK_ACCOUNT`` field
    pair (no formulas configured) keeps the historical withdrawal behaviour:
    the transfer is charged, the cash portion is handed out, the commission
    is the shop's income.
  * settlements only move toward the outstanding amount; a full settlement
    records Cash Book income and marks the invoice PAID
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from apps.common.services.formula import (
    FormulaError,
    ServicePassThroughType,
    evaluate,
)
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
from apps.customers.models import Customer
from apps.employees.models import WalletTransactionCategory, WalletType
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import BankAccount
from apps.finance.selectors.bank_selector import BankSelector
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


def _amount(value) -> Decimal:
    return Decimal(str(value or 0))


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
        where ``custom`` maps custom-field PKs (or variable names) to
        submitted values. Values are validated against the service's field
        definitions and the billing user's role, then snapshotted onto the
        invoice line.

        ``payments`` is an optional list of ``{"mode", "amount", "bank_account"}``
        dicts; when omitted the header ``payment_mode`` is used as a single
        full payment. Cash payments book Cash Book income + a staff CASH
        wallet credit; bank / UPI payments deposit into the chosen shop bank
        account + a staff ONLINE wallet credit; customer-wallet payments draw
        down the customer's pre-paid credit balance. The bank account can also
        come from a withdrawal line on the same bill.
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
            prepared.append(BillingService._resolve_line(service, qty, custom, by))

        subtotal = Decimal("0")
        for entry in prepared:
            subtotal += entry["amount"]

        discount = _amount(data.get("discount"))
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
                payments = [{"mode": payment_mode, "amount": total, "bank_account": data.get("bank_account")}]

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
            limit = _amount(customer.credit_limit)
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
            limit = _amount(customer.credit_limit)
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

        BillingService._validate_wallet_payments(cleaned_payments, customer)

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
            for entry in prepared:
                line = InvoiceLine.objects.create(
                    invoice=invoice,
                    service=entry["service"],
                    description=entry["service"].name,
                    qty=entry["qty"],
                    unit_price=entry["unit_price"],
                    amount=entry["amount"],
                    income_amount=entry["income_amount"],
                    created_by=by,
                    updated_by=by,
                )
                BillingService._store_field_values(line, entry["field_values"], by)
                if entry["bank_account"] is not None and withdrawal_default_bank is None:
                    withdrawal_default_bank = entry["bank_account"]
                if entry["passthrough"] > 0:
                    BillingService._book_passthrough(
                        invoice=invoice,
                        line=line,
                        passthrough=entry["passthrough"],
                        income=entry["income_amount"],
                        passthrough_type=entry["passthrough_type"],
                        party_name=party_name,
                        staff=staff,
                        by=by,
                    )

            first_cash_entry = None
            for payment in cleaned_payments:
                mode = payment["mode"]
                amount = payment["amount"]
                if mode == InvoicePaymentMode.CUSTOMER_WALLET:
                    BillingService._book_wallet_payment(
                        invoice=invoice,
                        customer=customer,
                        amount=amount,
                        by=by,
                    )
                    continue
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
                        bank_account = BankSelector.get_default_account()
                    if bank_account is None:
                        raise ValueError(
                            "UPI / bank payments need a shop bank account. Please create one in Finance > Bank Accounts first."
                        )
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

    # ------------------------------------------------------------------ lines

    @staticmethod
    def _resolve_line(service, qty, custom, by) -> dict:
        """Validate custom-field input and price one bill line.

        Returns a dict with ``amount`` (what the customer pays), ``income_amount``
        (what the shop keeps), ``passthrough_type`` and the legs to book. The
        pricing path is:

          * formulas configured -> evaluate against captured variables
            (``qty`` / ``price`` are always available)
          * a legacy ``BANK_TRANSFER`` pair (no formulas) -> the historical
            withdrawal: charge the transfer, hand out the cash, keep the
            commission
          * otherwise -> plain ``qty x price`` sale (income = full amount)
        """
        field_values, variables, transfer, percent_value, bank_account = (
            BillingService._resolve_custom_fields(service, qty, custom, by)
        )
        bank_account = bank_account or service.default_bank_account

        if service.total_formula and service.total_formula.strip():
            amount = BillingService._evaluate_formula(service.total_formula, variables, service)
            if amount <= 0:
                raise ValueError(f"Pricing formula for '{service.name}' produced a non-positive amount.")
            if service.income_formula and service.income_formula.strip():
                income = BillingService._evaluate_formula(service.income_formula, variables, service)
            else:
                income = amount
            if income < 0:
                raise ValueError(f"Income formula for '{service.name}' produced a negative income.")
            passthrough_type = service.passthrough_type or ServicePassThroughType.NONE
            unit_price = service.price
        elif transfer is not None:
            # Legacy BANK_TRANSFER pair: the historical cash-withdrawal.
            if bank_account is None:
                raise ValueError(
                    f"'{service.name}' needs a bank account field to deposit the transfer."
                )
            percent = percent_value or Decimal("0")
            cash_given = _round(transfer * Decimal("100") / (Decimal("100") + percent))
            commission = _round(transfer - cash_given)
            if commission < 0:
                raise ValueError("Commission cannot exceed the transfer amount.")
            amount = _round(Decimal(str(qty)) * transfer)
            income = _round(Decimal(str(qty)) * commission)
            passthrough_type = ServicePassThroughType.CASH
            unit_price = transfer
        else:
            amount = _round(Decimal(str(qty)) * Decimal(str(service.price)))
            income = amount
            passthrough_type = ServicePassThroughType.NONE
            unit_price = service.price

        passthrough = _round(amount - income)
        if passthrough < 0:
            raise ValueError(f"Income for '{service.name}' cannot exceed the charged amount.")
        return {
            "service": service,
            "qty": qty,
            "field_values": field_values,
            "unit_price": unit_price,
            "amount": amount,
            "income_amount": income,
            "passthrough_type": passthrough_type,
            "passthrough": passthrough,
            "bank_account": bank_account,
        }

    @staticmethod
    def _evaluate_formula(formula: str, variables: dict, service) -> Decimal:
        try:
            return _round(evaluate(formula, variables))
        except FormulaError as exc:
            raise ValueError(f"Formula error on '{service.name}': {exc}") from exc

    @staticmethod
    def _resolve_custom_fields(service, qty, custom_data, by):
        """Validate submitted custom-field values for the billing user's role.

        Returns ``(field_values, variables, transfer, percent_value, bank_account)``:
        ``field_values`` is a list of ``(field, value_text, bank_account)``
        tuples, ``variables`` maps variable names to Decimal values for the
        pricing formulas, and the last three carry the legacy BANK_TRANSFER
        withdrawal pair (``transfer`` / ``percent_value`` are None when no
        bank-transfer field is present).
        """
        custom_data = custom_data or {}
        field_values = []
        variables = {"qty": Decimal("1"), "price": _amount(service.price)}
        transfer_amount = None
        percent_value = None
        bank_account = None
        allowed_fields = ServiceSelector.visible_custom_fields(service, by)
        allowed_keys = {str(f.pk) for f in allowed_fields}

        for field in allowed_fields:
            raw = custom_data.get(str(field.pk))
            if raw is None:
                raw = custom_data.get(field.variable_name)
            value_text = ""
            account = None

            if field.field_type == CustomFieldType.BANK_ACCOUNT:
                if raw:
                    account = (
                        raw
                        if isinstance(raw, BankAccount)
                        else BankAccount.objects.filter(id=str(raw)).first()
                    )
                    if account is None:
                        raise ValueError(f"Invalid bank account for '{field.label}'.")
                elif service.default_bank_account:
                    account = service.default_bank_account
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
                    variables[field.variable_name] = amount
                if field.required and not raw:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            elif field.field_type == CustomFieldType.PERCENT:
                if raw:
                    percent = Decimal(str(raw))
                    if percent < 0 or percent > 100:
                        raise ValueError(f"'{field.label}' must be between 0 and 100.")
                    value_text = str(percent)
                    percent_value = percent
                    variables[field.variable_name] = percent
                if field.required and not raw:
                    raise ValueError(f"'{field.label}' is required for {service.name}.")

            elif field.field_type == CustomFieldType.NUMBER:
                if raw:
                    number = Decimal(str(raw))
                    if number < 0:
                        raise ValueError(f"'{field.label}' cannot be negative.")
                    value_text = str(_round(number))
                    variables[field.variable_name] = number
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

        allowed_names = {f.variable_name for f in allowed_fields}
        submitted_keys = {str(k) for k in (custom_data.keys() or [])}
        for key in submitted_keys:
            if key not in allowed_keys and key not in allowed_names and str(custom_data.get(key) or "").strip():
                field = ServiceCustomField.objects.filter(pk=key).first()
                label = field.label if field else "This field"
                raise ValueError(f"You do not have permission to set '{label}'.")

        variables["qty"] = _amount(qty)
        return field_values, variables, transfer_amount, percent_value, bank_account

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
    def _book_passthrough(
        *, invoice, line, passthrough, income, passthrough_type, party_name, staff, by=None
    ) -> None:
        """Book the pass-through side of a line.

        CASH passthrough (withdrawal / E-Sathi): the shop hands the customer
        cash out of the staff CASH wallet, books the cash-out expense and the
        commission it keeps. ONLINE passthrough (money transfer / form
        fill-up paid to a site): the money is sent out of the staff ONLINE
        wallet; no cash moves, so no cash-book entry.
        """
        reference = invoice.invoice_number
        if passthrough_type == ServicePassThroughType.CASH:
            if staff is not None:
                wallet = WalletService.get_or_create_wallet(staff, WalletType.CASH)
                txn = WalletService.debit(
                    wallet=wallet,
                    amount=passthrough,
                    category=WalletTransactionCategory.CASH_GIVEN,
                    description=f"Cash handed to customer ({reference})",
                    source=staff.full_name,
                    destination=party_name,
                    by=by,
                )
                line.wallet_entry_id = txn.id
            CashBookService.record_expense(
                amount=passthrough,
                category=CashEntryCategory.CASH_OUT,
                payment_mode="CASH",
                party_name=party_name,
                description=f"Cash given to customer ({reference})",
                by=by,
                staff=staff,
            )
        elif passthrough_type == ServicePassThroughType.ONLINE:
            if staff is not None:
                wallet = WalletService.get_or_create_wallet(staff, WalletType.ONLINE)
                txn = WalletService.debit(
                    wallet=wallet,
                    amount=passthrough,
                    category=WalletTransactionCategory.PAYOUT,
                    description=f"Transfer on behalf of customer ({reference})",
                    source=staff.full_name,
                    destination=party_name,
                    by=by,
                )
                line.wallet_entry_id = txn.id
        if line.wallet_entry_id or line.cash_entry_id:
            line.save(update_fields=["wallet_entry", "cash_entry", "updated_at"])

    # ----------------------------------------------------------- wallet payments

    @staticmethod
    def _validate_wallet_payments(payments: list, customer) -> None:
        """Customer-wallet payments require a customer with enough balance."""
        wallet_total = sum(p["amount"] for p in payments if p["mode"] == InvoicePaymentMode.CUSTOMER_WALLET)
        if wallet_total <= 0:
            return
        if customer is None:
            raise ValueError("Customer wallet payments require a customer.")
        if _amount(customer.credit_balance) < wallet_total:
            raise ValueError(
                f"Insufficient customer credit balance: has {customer.credit_balance}, "
                f"needs {wallet_total}."
            )

    @staticmethod
    @transaction.atomic
    def _book_wallet_payment(*, invoice: Invoice, customer: Customer, amount, by=None) -> InvoicePayment:
        """Draw down a customer's pre-paid credit balance as a payment."""
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        if _amount(customer.credit_balance) < amount:
            raise ValueError(
                f"Insufficient customer credit balance: has {customer.credit_balance}, needs {amount}."
            )
        customer.credit_balance = _amount(customer.credit_balance) - amount
        customer.updated_by = by
        customer.save(update_fields=["credit_balance", "updated_by", "updated_at"])
        return InvoicePayment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_mode=InvoicePaymentMode.CUSTOMER_WALLET,
            notes="Paid from customer pre-paid credit balance",
            created_by=by,
            updated_by=by,
        )

    # ------------------------------------------------------------ settlements

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
        if payment_mode == InvoicePaymentMode.CUSTOMER_WALLET:
            if invoice.customer is None:
                raise ValueError("Customer wallet payments require a customer.")
            payment = BillingService._book_wallet_payment(
                invoice=invoice,
                customer=invoice.customer,
                amount=amount,
                by=by,
            )
        else:
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
        wallet_payments = []
        for payment in invoice.payments.all():
            if payment.cash_entry is not None:
                entries.append(payment.cash_entry)
            if payment.bank_transaction is not None:
                bank_txns.append(payment.bank_transaction)
            if payment.payment_mode == InvoicePaymentMode.CUSTOMER_WALLET:
                wallet_payments.append(payment)
        for line in invoice.lines.all():
            if line.cash_entry is not None:
                entries.append(line.cash_entry)
            if line.bank_transaction is not None:
                bank_txns.append(line.bank_transaction)
        invoice.soft_delete(by=by)
        for entry in entries:
            if entry is not None and entry.is_active:
                entry.soft_delete(by=by)
        for txn in bank_txns:
            if txn is not None and txn.is_active:
                txn.soft_delete(by=by)
        for payment in wallet_payments:
            BillingService._refund_wallet_payment(payment, by=by)
        return invoice

    @staticmethod
    @transaction.atomic
    def _refund_wallet_payment(payment: InvoicePayment, *, by=None) -> None:
        """Return a customer-wallet payment to the customer's credit balance."""
        if payment.invoice.customer_id is None:
            return
        customer = Customer.objects.select_for_update().get(pk=payment.invoice.customer_id)
        customer.credit_balance = _amount(customer.credit_balance) + payment.amount
        customer.updated_by = by
        customer.save(update_fields=["credit_balance", "updated_by", "updated_at"])
        payment.soft_delete(by=by)


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
