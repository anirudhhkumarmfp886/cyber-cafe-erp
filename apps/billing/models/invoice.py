"""
Billing — invoices, bill lines and payments.

Every rupee on an invoice is derived from its lines (qty x snapshot price),
never typed in. A cash / UPI / card bill records its income into the Cash
Book atomically at creation; a credit bill stays UNPAID until settled, and
each settlement also lands in the Cash Book. Voiding (soft delete) reverses
the linked Cash Book entries so the ledger stays truthful.

Cash Out (E-Sathi) lives here too: the customer transfers into our bank
account, we hand over cash after cutting a manually-entered commission
percentage.
"""
from datetime import date

from django.db import models

from apps.common.models import BaseModel, money_field
from apps.customers.models import Customer
from apps.finance.models import BankAccount, CashBookEntry
from apps.services.models import Service


class InvoicePaymentMode(models.TextChoices):
    CASH = "CASH", "Cash"
    UPI = "UPI", "UPI"
    CARD = "CARD", "Card"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
    CREDIT = "CREDIT", "Credit / On Account"


class InvoiceStatus(models.TextChoices):
    PAID = "PAID", "Paid"
    PARTIAL = "PARTIAL", "Partially Paid"
    UNPAID = "UNPAID", "Unpaid"


class Invoice(BaseModel):
    invoice_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        help_text="Walk-in bills may leave this blank; credit bills require a customer.",
    )
    payment_mode = models.CharField(
        max_length=20,
        choices=InvoicePaymentMode.choices,
        default=InvoicePaymentMode.CASH,
        db_index=True,
    )
    status = models.CharField(
        max_length=10,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.UNPAID,
        db_index=True,
    )
    subtotal = money_field(default=0)
    discount = money_field(default=0)
    total = money_field(default=0)
    notes = models.TextField(blank=True)
    #: Cash Book income entry recorded when the invoice was paid (or, on
    #: credit, the first settlement). Kept so a void can reverse it.
    cash_entry = models.ForeignKey(
        CashBookEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    billed_on = models.DateField(default=date.today, db_index=True)

    class Meta:
        ordering = ["-billed_on", "-created_at"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        indexes = [
            models.Index(fields=["status", "billed_on"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} {self.total}"

    @property
    def paid_amount(self):
        total = self.payments.aggregate(paid=models.Sum("amount"))["paid"]
        return total or 0

    @property
    def outstanding_amount(self):
        return self.total - self.paid_amount


class InvoiceLine(BaseModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    #: Human-readable snapshot so the bill stays readable even if the
    #: service is later renamed.
    description = models.CharField(max_length=150)
    qty = models.DecimalField(max_digits=8, decimal_places=2)
    unit_price = money_field()
    amount = money_field()

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Invoice Line"
        verbose_name_plural = "Invoice Lines"

    def __str__(self):
        return f"{self.description} x {self.qty}"


class InvoicePayment(BaseModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = money_field()
    payment_mode = models.CharField(max_length=20, choices=InvoicePaymentMode.choices)
    payment_date = models.DateField(default=date.today, db_index=True)
    cash_entry = models.ForeignKey(
        CashBookEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]
        verbose_name = "Invoice Payment"
        verbose_name_plural = "Invoice Payments"

    def __str__(self):
        return f"{self.invoice.invoice_number} {self.payment_date} {self.amount}"


class CashOutStatus(models.TextChoices):
    DONE = "DONE", "Completed"


class CashOut(BaseModel):
    reference_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_outs",
    )
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="cash_outs",
    )
    transfer_amount = money_field()
    #: Commission the cafe keeps, entered manually as a percentage.
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2)
    commission_amount = money_field()
    cash_given = money_field()
    status = models.CharField(
        max_length=10,
        choices=CashOutStatus.choices,
        default=CashOutStatus.DONE,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    cash_out_on = models.DateField(default=date.today, db_index=True)

    class Meta:
        ordering = ["-cash_out_on", "-created_at"]
        verbose_name = "Cash Out"
        verbose_name_plural = "Cash Outs"

    def __str__(self):
        return f"{self.reference_number} transfer {self.transfer_amount}"
