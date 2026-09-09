"""
CustomerService — the only place customer records are created or changed.

Keeps the web layer thin and guarantees every entry point (forms, admin,
future API) applies the same rules.
"""
from decimal import Decimal

from django.db import transaction

from apps.customers.models import CreditLogType, Customer, CustomerCreditLog
from apps.employees.models import WalletTransactionCategory, WalletType
from apps.employees.services.wallet_service import WalletService
from apps.finance.models.enums import CashEntryCategory
from apps.finance.services.cashbook_service import CashBookService

_EDITABLE_FIELDS = (
    "full_name",
    "phone",
    "email",
    "gender",
    "date_of_birth",
    "address_line",
    "city",
    "state",
    "pincode",
    "credit_limit",
    "notes",
)


class CustomerService:
    @staticmethod
    @transaction.atomic
    def create_customer(*, data: dict, by=None) -> Customer:
        full_name = str(data.get("full_name", "")).strip()
        if not full_name:
            raise ValueError("Customer name is required.")

        phone = str(data.get("phone", "")).strip() or None
        if phone and Customer.objects.filter(phone=phone).exists():
            raise ValueError("A customer with this phone number already exists.")

        credit_limit = data.get("credit_limit")
        if credit_limit is not None and Decimal(str(credit_limit)) < 0:
            raise ValueError("Credit limit cannot be negative.")

        limit_val = Decimal(str(credit_limit or 0))

        customer = Customer.objects.create(
            full_name=full_name,
            phone=phone,
            email=data.get("email", ""),
            gender=data.get("gender", ""),
            date_of_birth=data.get("date_of_birth"),
            address_line=data.get("address_line", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            pincode=data.get("pincode", ""),
            credit_limit=limit_val,
            notes=data.get("notes", ""),
            created_by=by,
            updated_by=by,
        )

        if limit_val > 0:
            CustomerCreditLog.objects.create(
                customer=customer,
                log_type=CreditLogType.LIMIT_CHANGE,
                old_amount=0,
                new_amount=limit_val,
                change_amount=limit_val,
                notes=data.get("credit_limit_reason") or "Initial credit limit assigned",
                created_by=by,
            )

        return customer

    @staticmethod
    @transaction.atomic
    def update_customer(customer: Customer, *, data: dict, by=None) -> Customer:
        if "phone" in data:
            phone = str(data.get("phone", "")).strip() or None
            if phone:
                duplicate = (
                    Customer.all_objects.exclude(pk=customer.pk).filter(phone=phone).exists()
                )
                if duplicate:
                    raise ValueError("A customer with this phone number already exists.")
            data["phone"] = phone

        if "credit_limit" in data and data["credit_limit"] is not None:
            new_limit = Decimal(str(data["credit_limit"]))
            if new_limit < 0:
                raise ValueError("Credit limit cannot be negative.")
            old_limit = customer.credit_limit
            if new_limit != old_limit:
                CustomerCreditLog.objects.create(
                    customer=customer,
                    log_type=CreditLogType.LIMIT_CHANGE,
                    old_amount=old_limit,
                    new_amount=new_limit,
                    change_amount=new_limit - old_limit,
                    notes=data.get("credit_limit_reason") or "Credit limit updated",
                    created_by=by,
                )

        for field in _EDITABLE_FIELDS:
            if field in data:
                setattr(customer, field, data[field])
        customer.updated_by = by
        customer.save()
        return customer

    @staticmethod
    def deactivate_customer(customer: Customer, *, by=None) -> Customer:
        return customer.soft_delete(by=by)

    @staticmethod
    def restore_customer(customer: Customer, *, by=None) -> Customer:
        return customer.restore(by=by)

    @staticmethod
    @transaction.atomic
    def adjust_credit(
        *,
        customer: Customer,
        amount,
        payment_mode: str = "CASH",
        payment_destination: str = "STAFF",
        description: str = "",
        by=None,
    ) -> Customer:
        """Change the customer's pre-paid credit balance and route funds to staff wallet.

        ``amount > 0`` is a deposit (cash book / staff wallet credited);
        ``amount < 0`` is a refund.
        """
        amount = Decimal(str(amount or 0))
        if amount == 0:
            raise ValueError("Credit amount must not be zero.")

        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        old_balance = customer.credit_balance
        new_balance = customer.credit_balance + amount
        if new_balance < 0:
            raise ValueError("Refund exceeds the customer's current credit balance.")

        party = customer.full_name
        staff = getattr(by, "employee", None) if by else None

        if amount > 0:
            # Deposit
            if payment_mode == "CASH":
                if payment_destination == "STAFF" and staff:
                    CashBookService.record_income(
                        amount=amount,
                        category=CashEntryCategory.OTHER_INCOME,
                        payment_mode="CASH",
                        party_name=party,
                        staff=staff,
                        description=description or f"Customer advance deposit for {party}",
                        by=by,
                    )
                    WalletService.credit(
                        wallet=WalletService.get_or_create_wallet(staff, WalletType.CASH),
                        amount=amount,
                        category=WalletTransactionCategory.PAYMENT_COLLECTED,
                        description=description or f"Customer advance deposit from {party}",
                        source=party,
                        destination=staff.full_name,
                        by=by,
                    )
                else:
                    CashBookService.record_income(
                        amount=amount,
                        category=CashEntryCategory.OTHER_INCOME,
                        payment_mode="CASH",
                        party_name=party,
                        staff=None,
                        description=description or f"Customer advance deposit for {party}",
                        by=by,
                    )
            elif payment_mode == "STAFF_UPI":
                if staff:
                    WalletService.credit(
                        wallet=WalletService.get_or_create_wallet(staff, WalletType.ONLINE),
                        amount=amount,
                        category=WalletTransactionCategory.PAYMENT_COLLECTED,
                        description=description or f"Customer advance UPI deposit from {party}",
                        source=party,
                        destination=staff.full_name,
                        by=by,
                    )
            elif payment_mode == "SHOP_UPI":
                CashBookService.record_income(
                    amount=amount,
                    category=CashEntryCategory.OTHER_INCOME,
                    payment_mode="UPI",
                    party_name=party,
                    staff=None,
                    description=description or f"Customer advance Shop UPI deposit for {party}",
                    by=by,
                )

            CustomerCreditLog.objects.create(
                customer=customer,
                log_type=CreditLogType.PREPAID_DEPOSIT,
                old_amount=old_balance,
                new_amount=new_balance,
                change_amount=amount,
                payment_mode=payment_mode,
                payment_destination=payment_destination,
                notes=description or "Advance deposit received",
                created_by=by,
            )
        else:
            # Refund (amount is negative)
            refund_amount = -amount
            if payment_mode == "CASH":
                if payment_destination == "STAFF" and staff:
                    CashBookService.record_expense(
                        amount=refund_amount,
                        category=CashEntryCategory.MISC,
                        payment_mode="CASH",
                        party_name=party,
                        staff=staff,
                        description=description or f"Customer credit refund for {party}",
                        by=by,
                    )
                    WalletService.debit(
                        wallet=WalletService.get_or_create_wallet(staff, WalletType.CASH),
                        amount=refund_amount,
                        category=WalletTransactionCategory.EXPENSE,
                        description=description or f"Customer credit refund to {party}",
                        source=staff.full_name,
                        destination=party,
                        by=by,
                    )
                else:
                    CashBookService.record_expense(
                        amount=refund_amount,
                        category=CashEntryCategory.MISC,
                        payment_mode="CASH",
                        party_name=party,
                        staff=None,
                        description=description or f"Customer credit refund for {party}",
                        by=by,
                    )

            CustomerCreditLog.objects.create(
                customer=customer,
                log_type=CreditLogType.PREPAID_REFUND,
                old_amount=old_balance,
                new_amount=new_balance,
                change_amount=amount,
                payment_mode=payment_mode,
                payment_destination=payment_destination,
                notes=description or "Advance balance refund",
                created_by=by,
            )

        customer.credit_balance = new_balance
        customer.updated_by = by
        customer.save(update_fields=["credit_balance", "updated_by", "updated_at"])
        return customer
