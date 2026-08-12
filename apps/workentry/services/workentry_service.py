"""
WorkEntryService — the only place work entries move money.

A work entry is created as a DRAFT on the counter page; ``finalize`` (the
"Save Bill" step) books every ledger atomically and marks it SAVED. Rules
enforced here (and nowhere else in the web layer):

  * the customer pays ``charged + transfers + cash_withdrawal`` through the
    chosen payment mode
  * income is ALWAYS the charged amount (SALES income in the cash book) —
    the transfers and the cash withdrawal are pass-through
  * cash collected credits the staff CASH wallet; online / bank payments
    deposit into the chosen shop bank account AND credit the staff ONLINE
    wallet (so a later ledger can reverse everything traceably)
  * a transfer to the customer's account / on their behalf debits the staff
    ONLINE wallet; a cash withdrawal debits the staff CASH wallet (both are
    pass-through legs — no duplicate cash book / bank expense)
  * customer credit settles against the customer's pre-paid credit_balance
    first; the rest is collected now (CASH or online) and credited to the
    belonging staff wallet
"""
from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.common.services.reference_service import ReferenceService
from apps.customers.models import Customer
from apps.employees.models import WalletTransactionCategory, WalletType
from apps.employees.services.wallet_service import WalletService
from apps.finance.models import BankAccount
from apps.finance.models.enums import BankTransactionCategory, CashEntryCategory
from apps.finance.services.bank_service import BankService
from apps.finance.services.cashbook_service import CashBookService
from apps.workentry.models import WorkEntry, WorkEntryStatus, WorkPaymentMode


def _amount(value) -> Decimal:
    return Decimal(str(value or 0))


class WorkEntryService:
    @staticmethod
    @transaction.atomic
    def create_draft(*, data: dict, by=None) -> WorkEntry:
        """Create a DRAFT work entry from the counter form.

        Full business validation happens at finalize (the bill is editable);
        here we only reject obviously broken drafts so the ledger never sees
        junk. ``by`` must be an employee.
        """
        staff = getattr(by, "employee", None)
        if staff is None:
            raise ValueError("Only employees can record work entries.")

        service = data.get("service")
        if service is None:
            raise ValueError("Select a work type / service.")
        if not service.is_active:
            raise ValueError(f"Service '{service.name}' is inactive and cannot be billed.")

        charged = _amount(data.get("charged_amount"))
        transfer_to_customer = _amount(data.get("transfer_to_customer"))
        transfer_on_behalf = _amount(data.get("transfer_on_behalf"))
        cash_withdrawal = _amount(data.get("cash_withdrawal"))
        if min(charged, transfer_to_customer, transfer_on_behalf, cash_withdrawal) < 0:
            raise ValueError("Amounts cannot be negative.")
        total = charged + transfer_to_customer + transfer_on_behalf + cash_withdrawal
        if total <= 0:
            raise ValueError("Enter at least one amount.")

        page_qty = data.get("page_quantity")
        if page_qty is not None and _amount(page_qty) < 0:
            raise ValueError("Page quantity cannot be negative.")

        customer = data.get("customer")
        customer_name = customer.full_name if customer else str(data.get("customer_name") or "").strip()

        return WorkEntry.objects.create(
            reference_number=ReferenceService.next(ReferenceService.WORK_ENTRY),
            employee=staff,
            entry_date=data.get("entry_date") or date.today(),
            customer=customer,
            customer_name=customer_name,
            service=service,
            page_quantity=page_qty or 0,
            charged_amount=charged,
            payment_mode=data.get("payment_mode") or WorkPaymentMode.CASH,
            credit_rest_mode=data.get("credit_rest_mode") or "",
            bank_account=data.get("bank_account"),
            transfer_to_customer=transfer_to_customer,
            transfer_on_behalf=transfer_on_behalf,
            cash_withdrawal=cash_withdrawal,
            notes=data.get("notes", ""),
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    @transaction.atomic
    def finalize(*, entry: WorkEntry, by=None) -> WorkEntry:
        """Save the bill: re-validate, book every ledger, mark the entry SAVED.

        Raises ``ValueError`` on any rule violation; nothing is booked unless
        the whole save succeeds (single atomic transaction).
        """
        entry = (
            WorkEntry.objects.select_for_update()
            .select_related("employee", "customer", "service")
            .get(pk=entry.pk)
        )
        if entry.status == WorkEntryStatus.SAVED:
            raise ValueError("This work entry is already saved.")

        charged = _amount(entry.charged_amount)
        transfer_to_customer = _amount(entry.transfer_to_customer)
        transfer_on_behalf = _amount(entry.transfer_on_behalf)
        cash_withdrawal = _amount(entry.cash_withdrawal)
        if min(charged, transfer_to_customer, transfer_on_behalf, cash_withdrawal) < 0:
            raise ValueError("Amounts cannot be negative.")
        total = charged + transfer_to_customer + transfer_on_behalf + cash_withdrawal
        if total <= 0:
            raise ValueError("Enter at least one amount.")

        staff = entry.employee
        party = entry.customer_display
        reference = entry.reference_number
        mode = entry.payment_mode

        cash_wallet = WalletService.get_or_create_wallet(staff, WalletType.CASH)
        online_wallet = WalletService.get_or_create_wallet(staff, WalletType.ONLINE)

        # ---- Collection (credit wallets first so float covers the legs) ----
        if mode == WorkPaymentMode.CASH:
            if total > 0:
                WalletService.credit(
                    wallet=cash_wallet,
                    amount=total,
                    category=WalletTransactionCategory.PAYMENT_COLLECTED,
                    description=f"Cash collected for {reference}",
                    source=party,
                    destination=staff.full_name,
                    by=by,
                    entry_date=entry.entry_date,
                )
        elif mode in (WorkPaymentMode.UPI, WorkPaymentMode.CARD, WorkPaymentMode.BANK_TRANSFER):
            if total > 0:
                bank_account = WorkEntryService._required_bank(entry)
                BankService.deposit(
                    account=bank_account,
                    amount=total,
                    category=BankTransactionCategory.PAYMENT_RECEIVED,
                    party_name=party,
                    description=f"{mode} payment for {reference}",
                    entry_date=entry.entry_date,
                    by=by,
                )
                WalletService.credit(
                    wallet=online_wallet,
                    amount=total,
                    category=WalletTransactionCategory.PAYMENT_COLLECTED,
                    description=f"{mode} payment for {reference}",
                    source=party,
                    destination=staff.full_name,
                    by=by,
                    entry_date=entry.entry_date,
                )
        elif mode == WorkPaymentMode.CUSTOMER_CREDIT:
            if entry.customer is None:
                raise ValueError("Customer credit requires a customer.")
            customer = Customer.objects.select_for_update().get(pk=entry.customer.pk)
            credit = _amount(customer.credit_balance)
            settled = min(total, credit)
            rest = total - settled
            entry.credit_used = settled
            if settled > 0:
                customer.credit_balance = credit - settled
                customer.updated_by = by
                customer.save(update_fields=["credit_balance", "updated_by", "updated_at"])
            if rest > 0:
                rest_mode = entry.credit_rest_mode
                if not rest_mode:
                    raise ValueError("Choose how the rest (beyond customer credit) is paid.")
                if rest_mode == WorkPaymentMode.CASH:
                    WalletService.credit(
                        wallet=cash_wallet,
                        amount=rest,
                        category=WalletTransactionCategory.PAYMENT_COLLECTED,
                        description=f"Rest cash payment for {reference}",
                        source=party,
                        destination=staff.full_name,
                        by=by,
                        entry_date=entry.entry_date,
                    )
                else:
                    bank_account = WorkEntryService._required_bank(entry)
                    BankService.deposit(
                        account=bank_account,
                        amount=rest,
                        category=BankTransactionCategory.PAYMENT_RECEIVED,
                        party_name=party,
                        description=f"Rest {rest_mode} payment for {reference}",
                        entry_date=entry.entry_date,
                        by=by,
                    )
                    WalletService.credit(
                        wallet=online_wallet,
                        amount=rest,
                        category=WalletTransactionCategory.PAYMENT_COLLECTED,
                        description=f"Rest {rest_mode} payment for {reference}",
                        source=party,
                        destination=staff.full_name,
                        by=by,
                        entry_date=entry.entry_date,
                    )

        # ---- Legs (staff wallet debits only — pass-through, no duplicate
        #      cash book / bank expense per the design decision) ----
        if cash_withdrawal > 0:
            WalletService.debit(
                wallet=cash_wallet,
                amount=cash_withdrawal,
                category=WalletTransactionCategory.CASH_GIVEN,
                description=f"Cash handed to customer ({reference})",
                source=staff.full_name,
                destination=party,
                by=by,
                entry_date=entry.entry_date,
            )
        if transfer_to_customer > 0:
            WalletService.debit(
                wallet=online_wallet,
                amount=transfer_to_customer,
                category=WalletTransactionCategory.PAYOUT,
                description=f"Transfer to customer's account ({reference})",
                source=staff.full_name,
                destination=party,
                by=by,
                entry_date=entry.entry_date,
            )
        if transfer_on_behalf > 0:
            WalletService.debit(
                wallet=online_wallet,
                amount=transfer_on_behalf,
                category=WalletTransactionCategory.PAYOUT,
                description=f"Transfer on behalf of customer ({reference})",
                source=staff.full_name,
                destination=party,
                by=by,
                entry_date=entry.entry_date,
            )

        # ---- Income (the shop keeps only the charged amount) ----
        if charged > 0:
            CashBookService.record_income(
                amount=charged,
                category=CashEntryCategory.SALES,
                payment_mode=WorkEntryService._cashbook_mode(entry),
                party_name=party,
                description=f"Work entry {reference} ({entry.service.name})",
                entry_date=entry.entry_date,
                by=by,
                staff=staff,
            )

        entry.total = total
        entry.income = charged
        entry.status = WorkEntryStatus.SAVED
        entry.updated_by = by
        entry.save(
            update_fields=[
                "total",
                "income",
                "status",
                "credit_used",
                "updated_by",
                "updated_at",
            ]
        )
        return entry

    @staticmethod
    def _required_bank(entry: WorkEntry) -> BankAccount:
        if entry.bank_account is None:
            raise ValueError("UPI / bank payments need a shop bank account.")
        return BankAccount.objects.select_for_update().get(pk=entry.bank_account.pk)

    @staticmethod
    def _cashbook_mode(entry: WorkEntry) -> str:
        """Map a work payment mode to a valid cash book payment mode."""
        if entry.payment_mode == WorkPaymentMode.CUSTOMER_CREDIT:
            return entry.credit_rest_mode or WorkPaymentMode.CASH
        return entry.payment_mode
