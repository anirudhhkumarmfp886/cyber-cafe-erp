"""
CustomerService — the only place customer records are created or changed.

Keeps the web layer thin and guarantees every entry point (forms, admin,
future API) applies the same rules.
"""
from decimal import Decimal

from django.db import transaction

from apps.customers.models import Customer
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
    def create_customer(*, data: dict, by=None) -> Customer:
        full_name = str(data.get("full_name", "")).strip()
        if not full_name:
            raise ValueError("Customer name is required.")

        phone = str(data.get("phone", "")).strip()
        if phone and Customer.objects.filter(phone=phone).exists():
            raise ValueError("A customer with this phone number already exists.")

        credit_limit = data.get("credit_limit")
        if credit_limit is not None and credit_limit < 0:
            raise ValueError("Credit limit cannot be negative.")

        return Customer.objects.create(
            full_name=full_name,
            phone=phone,
            email=data.get("email", ""),
            gender=data.get("gender", ""),
            date_of_birth=data.get("date_of_birth"),
            address_line=data.get("address_line", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            pincode=data.get("pincode", ""),
            credit_limit=credit_limit or 0,
            notes=data.get("notes", ""),
            created_by=by,
            updated_by=by,
        )

    @staticmethod
    def update_customer(customer: Customer, *, data: dict, by=None) -> Customer:
        phone = str(data.get("phone", "")).strip()
        if phone:
            duplicate = (
                Customer.all_objects.exclude(pk=customer.pk).filter(phone=phone).exists()
            )
            if duplicate:
                raise ValueError("A customer with this phone number already exists.")

        credit_limit = data.get("credit_limit")
        if credit_limit is not None and credit_limit < 0:
            raise ValueError("Credit limit cannot be negative.")

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
    def adjust_credit(*, customer: Customer, amount, description: str = "", by=None) -> Customer:
        """Change the customer's pre-paid credit balance.

        ``amount > 0`` is a deposit (cash book OTHER_INCOME entry booked);
        ``amount < 0`` is a refund. Used for the CUSTOMER_CREDIT payment mode
        on work entries — the balance is drawn down there by the work entry
        service, not here.
        """
        amount = Decimal(str(amount or 0))
        if amount == 0:
            raise ValueError("Credit amount must not be zero.")

        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        new_balance = customer.credit_balance + amount
        if new_balance < 0:
            raise ValueError("Refund exceeds the customer's current credit balance.")

        party = customer.full_name
        if amount > 0:
            CashBookService.record_income(
                amount=amount,
                category=CashEntryCategory.OTHER_INCOME,
                payment_mode="CASH",
                party_name=party,
                description=description or f"Customer credit deposit for {party}",
                by=by,
            )
        else:
            CashBookService.record_expense(
                amount=-amount,
                category=CashEntryCategory.MISC,
                payment_mode="CASH",
                party_name=party,
                description=description or f"Customer credit refund for {party}",
                by=by,
            )

        customer.credit_balance = new_balance
        customer.updated_by = by
        customer.save(update_fields=["credit_balance", "updated_by", "updated_at"])
        return customer
