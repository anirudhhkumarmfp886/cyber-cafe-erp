"""
CustomerSelector — read-only access to customer data for views/templates.
"""
from decimal import Decimal

from django.db.models import Q

from apps.billing.models import Invoice, InvoiceStatus
from apps.customers.models import CreditLogType, Customer, CustomerCreditLog


class CustomerSelector:
    @staticmethod
    def list_customers(search: str = ""):
        queryset = Customer.objects.all()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return queryset.order_by("-created_at")

    @staticmethod
    def get_by_id(customer_id):
        return Customer.objects.filter(id=customer_id).first()

    @staticmethod
    def count_active() -> int:
        return Customer.objects.count()

    @staticmethod
    def get_invoices(customer: Customer):
        return (
            Invoice.objects.filter(customer=customer)
            .select_related("created_by")
            .prefetch_related("payments")
            .order_by("-billed_on", "-created_at")
        )

    @staticmethod
    def get_financial_summary(customer: Customer) -> dict:
        invoices = CustomerSelector.get_invoices(customer)
        total_billed = sum((inv.total for inv in invoices), Decimal("0"))
        total_paid = sum((inv.paid_amount for inv in invoices), Decimal("0"))
        outstanding_due = sum((inv.outstanding_amount for inv in invoices if inv.status != InvoiceStatus.PAID), Decimal("0"))
        
        limit = customer.credit_limit or Decimal("0")
        available_limit = max(Decimal("0"), limit - outstanding_due)

        return {
            "credit_limit": limit,
            "credit_balance": customer.credit_balance or Decimal("0"),
            "total_billed": total_billed,
            "total_paid": total_paid,
            "outstanding_due": outstanding_due,
            "available_limit": available_limit,
            "total_invoices_count": invoices.count(),
            "unpaid_invoices_count": invoices.exclude(status=InvoiceStatus.PAID).count(),
        }

    @staticmethod
    def get_credit_logs(customer: Customer):
        return (
            CustomerCreditLog.objects.filter(customer=customer)
            .select_related("created_by", "invoice")
            .order_by("-created_at")
        )

    @staticmethod
    def get_prepaid_logs(customer: Customer):
        return (
            CustomerCreditLog.objects.filter(
                customer=customer,
                log_type__in=[
                    CreditLogType.PREPAID_DEPOSIT,
                    CreditLogType.PREPAID_USAGE,
                    CreditLogType.PREPAID_REFUND,
                ],
            )
            .select_related("created_by", "invoice")
            .order_by("-created_at")
        )

    @staticmethod
    def get_limit_logs(customer: Customer):
        return (
            CustomerCreditLog.objects.filter(
                customer=customer,
                log_type=CreditLogType.LIMIT_CHANGE,
            )
            .select_related("created_by")
            .order_by("-created_at")
        )
