"""
InvoiceSelector — read-only access to invoices, payments and cash-outs.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from apps.billing.models import CashOut, Invoice, InvoiceLine, InvoiceStatus
from apps.customers.models import Customer


class InvoiceSelector:
    @staticmethod
    def list_invoices(filters: dict):
        queryset = Invoice.objects.select_related("customer").order_by("-billed_on", "-created_at")
        status = filters.get("status")
        from_date = filters.get("from_date")
        to_date = filters.get("to_date")
        q = filters.get("q", "")
        if status:
            queryset = queryset.filter(status=status)
        if from_date:
            queryset = queryset.filter(billed_on__gte=from_date)
        if to_date:
            queryset = queryset.filter(billed_on__lte=to_date)
        if q:
            queryset = queryset.filter(
                Q(customer__full_name__icontains=q)
                | Q(invoice_number__icontains=q)
            )
        return queryset

    @staticmethod
    def get_by_id(invoice_id):
        return Invoice.objects.filter(id=invoice_id).first()

    @staticmethod
    def lines(invoice):
        return invoice.lines.select_related("service").order_by("created_at")

    @staticmethod
    def payments(invoice):
        return invoice.payments.order_by("-payment_date", "-created_at")

    @staticmethod
    def outstanding_for_customer(customer: Customer) -> Decimal:
        """Sum of everything a customer still owes (open invoices only)."""
        open_invoices = Invoice.objects.filter(customer=customer).exclude(
            status=InvoiceStatus.PAID
        )
        total = Decimal("0")
        for invoice in open_invoices:
            total += invoice.total - invoice.paid_amount
        return total

    @staticmethod
    def list_cash_outs(filters: dict):
        queryset = CashOut.objects.select_related("customer", "bank_account").order_by(
            "-cash_out_on", "-created_at"
        )
        from_date = filters.get("from_date")
        to_date = filters.get("to_date")
        if from_date:
            queryset = queryset.filter(cash_out_on__gte=from_date)
        if to_date:
            queryset = queryset.filter(cash_out_on__lte=to_date)
        return queryset

    @staticmethod
    def today_billing_total():
        total = (
            Invoice.objects.filter(billed_on=date.today()).aggregate(
                total=Coalesce(Sum("total"), Decimal("0"))
            )["total"]
        )
        return total or 0

    @staticmethod
    def pending_count() -> int:
        return (
            Invoice.objects.exclude(status=InvoiceStatus.PAID)
            .values("id")
            .count()
        )

    @staticmethod
    def pending_total():
        """Outstanding rupee amount across all open invoices."""
        open_invoices = Invoice.objects.exclude(status=InvoiceStatus.PAID)
        total = Decimal("0")
        for invoice in open_invoices:
            total += invoice.total - invoice.paid_amount
        return total

    @staticmethod
    def top_services(days: int = 30, limit: int = 5):
        """Most-revenue services over the last ``days`` days, by billed lines."""
        since = date.today() - timedelta(days=days)
        return (
            InvoiceLine.objects.filter(invoice__billed_on__gte=since)
            .values("service_id", "description")
            .annotate(qty=Sum("qty"), revenue=Coalesce(Sum("amount"), Decimal("0")))
            .order_by("-revenue")[:limit]
        )

    @staticmethod
    def customers_with_outstanding():
        """Active customers ordered by how much they still owe."""
        rows = []
        for customer in Customer.objects.all().order_by("full_name"):
            outstanding = InvoiceSelector.outstanding_for_customer(customer)
            if outstanding > 0:
                rows.append({"customer": customer, "outstanding": outstanding})
        return rows
