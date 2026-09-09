"""
UPIBookService — manages shop digital/UPI operational float and ledger entries.

Handles:
- Loading daily float from reserve bank account (Bank -> UPI Book)
- Distributing online float to staff online wallets (UPI Book -> Staff Online Wallet)
- Recording customer UPI payments / QR soundbox settlements
- Reimbursing staff cash float from UPI pool
- Returning staff online float back to UPI Book
- Sweeping float and profits back to bank accounts (UPI Book -> Bank)
"""
from datetime import date

from django.db import transaction
from django.db.models import Case, F, Sum, When

from apps.common.services.reference_service import ReferenceService
from apps.finance.models.bank import BankAccount
from apps.finance.models.enums import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    BankTransactionCategory,
    CashEntryCategory,
    CashEntryType,
)
from apps.finance.models.upibook import UPIBookEntry
from apps.finance.services.bank_service import BankService


class UPIBookService:
    @staticmethod
    def record_income(
        *,
        amount,
        category: str = CashEntryCategory.SALES,
        bank_account: BankAccount | None = None,
        party_name: str = "",
        description: str = "",
        entry_date=None,
        by=None,
        staff=None,
    ) -> UPIBookEntry:
        return UPIBookService._record(
            entry_type=CashEntryType.INCOME,
            amount=amount,
            category=category,
            bank_account=bank_account,
            party_name=party_name,
            description=description,
            entry_date=entry_date,
            by=by,
            staff=staff,
        )

    @staticmethod
    def record_expense(
        *,
        amount,
        category: str = CashEntryCategory.MISC,
        bank_account: BankAccount | None = None,
        party_name: str = "",
        description: str = "",
        entry_date=None,
        by=None,
        staff=None,
    ) -> UPIBookEntry:
        return UPIBookService._record(
            entry_type=CashEntryType.EXPENSE,
            amount=amount,
            category=category,
            bank_account=bank_account,
            party_name=party_name,
            description=description,
            entry_date=entry_date,
            by=by,
            staff=staff,
        )

    @staticmethod
    def _record(
        *,
        entry_type: str,
        amount,
        category: str,
        bank_account: BankAccount | None,
        party_name: str,
        description: str,
        entry_date,
        by,
        staff,
    ) -> UPIBookEntry:
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        valid_categories = INCOME_CATEGORIES if entry_type == CashEntryType.INCOME else EXPENSE_CATEGORIES
        if category not in valid_categories:
            raise ValueError(f"Category '{category}' is not valid for {entry_type} entries.")

        responsible_staff = staff
        if responsible_staff is None and by is not None:
            responsible_staff = getattr(by, "employee", None)

        with transaction.atomic():
            return UPIBookEntry.objects.create(
                entry_date=entry_date or date.today(),
                entry_type=entry_type,
                category=category,
                amount=amount,
                reference_number=ReferenceService.next(ReferenceService.UPI_BOOK),
                bank_account=bank_account,
                party_name=party_name,
                description=description,
                staff=responsible_staff,
                created_by=by,
                updated_by=by,
            )

    @staticmethod
    def balance(staff=None) -> float:
        """Current UPI book balance = total income - total expense."""
        qs = UPIBookEntry.objects.all()
        if staff is not None:
            qs = qs.filter(staff=staff)
        total = qs.aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    def day_balance(day, staff=None) -> float:
        """UPI balance at the end of a given day."""
        qs = UPIBookEntry.objects.filter(entry_date__lte=day)
        if staff is not None:
            qs = qs.filter(staff=staff)
        total = qs.aggregate(
            net=Sum(
                Case(
                    When(entry_type=CashEntryType.INCOME, then=F("amount")),
                    default=-F("amount"),
                )
            )
        )["net"]
        return total or 0

    @staticmethod
    @transaction.atomic
    def fund_from_bank(
        *,
        bank_account: BankAccount,
        amount,
        description: str = "",
        entry_date=None,
        by=None,
    ) -> tuple[UPIBookEntry, any]:
        """Transfers float from Reserve Bank Account into Shop UPI Book.

        Bank account is debited (WITHDRAWAL).
        UPI Book is credited (OWNER_DEPOSIT).
        """
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        if bank_account.balance < amount:
            raise ValueError(
                f"Insufficient bank balance in {bank_account.account_name} "
                f"(Available: ₹{bank_account.balance:.2f})."
            )

        entry_date = entry_date or date.today()
        bank_txn = BankService.withdraw(
            account=bank_account,
            amount=amount,
            category=BankTransactionCategory.WITHDRAWAL,
            party_name="Shop UPI Book",
            description=f"Float transfer to Shop UPI Book. {description}".strip(),
            entry_date=entry_date,
            by=by,
        )
        upi_entry = UPIBookService.record_income(
            amount=amount,
            category=CashEntryCategory.OWNER_DEPOSIT,
            bank_account=bank_account,
            party_name="Reserve Bank",
            description=f"Transferred float from {bank_account.account_name} ({bank_account.bank_name}) [Ref: {bank_txn.reference_number}]. {description}".strip(),
            entry_date=entry_date,
            by=by,
        )
        bank_txn.related_reference = upi_entry.reference_number
        bank_txn.save(update_fields=["related_reference", "updated_at"])
        return upi_entry, bank_txn

    @staticmethod
    @transaction.atomic
    def sweep_to_bank(
        *,
        bank_account: BankAccount,
        amount,
        category: str = CashEntryCategory.OWNER_WITHDRAWAL,
        description: str = "",
        entry_date=None,
        by=None,
    ) -> tuple[UPIBookEntry, any]:
        """Sweeps float or profits from Shop UPI Book into Bank Account.

        UPI Book is debited (OWNER_WITHDRAWAL).
        Bank account is credited (DEPOSIT).
        """
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        current_bal = UPIBookService.balance()
        if amount > current_bal:
            raise ValueError(
                f"Insufficient UPI Book balance to sweep ₹{amount:.2f} "
                f"(Available in UPI Book: ₹{current_bal:.2f})."
            )

        entry_date = entry_date or date.today()
        upi_entry = UPIBookService.record_expense(
            amount=amount,
            category=category,
            bank_account=bank_account,
            party_name=bank_account.bank_name,
            description=f"Deposited into {bank_account.account_name} ({bank_account.bank_name}). {description}".strip(),
            entry_date=entry_date,
            by=by,
        )
        bank_txn = BankService.deposit(
            account=bank_account,
            amount=amount,
            category=BankTransactionCategory.DEPOSIT,
            party_name="Shop UPI Book",
            description=f"Deposit from Shop UPI Book [Ref: {upi_entry.reference_number}]. {description}".strip(),
            entry_date=entry_date,
            by=by,
        )
        bank_txn.related_reference = upi_entry.reference_number
        bank_txn.save(update_fields=["related_reference", "updated_at"])
        return upi_entry, bank_txn

    @staticmethod
    @transaction.atomic
    def reimburse_cash_float(
        *,
        amount,
        staff=None,
        description: str = "",
        entry_date=None,
        by=None,
    ) -> tuple[UPIBookEntry, any]:
        """Reimburses cash float to staff or cash drawer from UPI pool.

        UPI Book is debited (REIMBURSEMENT).
        Staff Cash Wallet or Shop Cash Drawer is credited (FLOAT_IN).
        """
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        current_bal = UPIBookService.balance()
        if amount > current_bal:
            raise ValueError(
                f"Insufficient UPI Book balance to reimburse ₹{amount:.2f} "
                f"(Available in UPI Book: ₹{current_bal:.2f})."
            )

        entry_date = entry_date or date.today()
        party = staff.full_name if staff else "Shop Cash Drawer"
        upi_entry = UPIBookService.record_expense(
            amount=amount,
            category=CashEntryCategory.REIMBURSEMENT,
            party_name=party,
            description=f"Cash float reimbursement to {party}. {description}".strip(),
            entry_date=entry_date,
            by=by,
            staff=staff,
        )

        if staff is not None:
            from apps.employees.models import WalletTransactionCategory, WalletType
            from apps.employees.services.wallet_service import WalletService

            wallet = WalletService.get_or_create_wallet(staff, WalletType.CASH)
            wallet_txn = WalletService.credit(
                wallet=wallet,
                amount=amount,
                category=WalletTransactionCategory.FLOAT_IN,
                description=f"Cash float reimbursement from Shop UPI Book [Ref: {upi_entry.reference_number}]. {description}".strip(),
                source="Shop UPI Book",
                destination=staff.full_name,
                by=by,
                entry_date=entry_date,
            )
            return upi_entry, wallet_txn
        else:
            from apps.finance.services.cashbook_service import CashBookService

            cb_entry = CashBookService.record_income(
                amount=amount,
                category=CashEntryCategory.FLOAT_IN,
                payment_mode="CASH",
                party_name="Shop UPI Book",
                description=f"Cash float replenishment from Shop UPI Book [Ref: {upi_entry.reference_number}]. {description}".strip(),
                entry_date=entry_date,
                by=by,
            )
            return upi_entry, cb_entry

    @staticmethod
    def soft_delete_entry(entry: UPIBookEntry, *, by=None) -> UPIBookEntry:
        return entry.soft_delete(by=by)

