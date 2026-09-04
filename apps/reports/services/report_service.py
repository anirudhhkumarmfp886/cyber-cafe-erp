"""
ReportService — read-only aggregations behind every report page and its CSV
export. Views stay thin; all the date-range filtering lives here.

Reports:
  * profit_loss     — cash book income/expense by category + net
  * bank_statement  — per-account transaction statement with running balance
  * customer_ledger — invoices billed in range, paid vs outstanding
  * wallet_statement— per-employee wallet ledger
  * salary_summary  — approved work log wages grouped by employee
  * analytics       — peak hours, top services, per-employee sales
"""
import csv
from decimal import Decimal

from django.db.models import Case, Count, F, Sum, When
from django.db.models.functions import Coalesce, TruncHour
from django.http import HttpResponse

from apps.billing.models import Invoice, InvoiceLine, InvoicePayment
from apps.employees.models import Employee, WalletTransaction, WorkLogEntry, WorkLogStatus
from apps.finance.models import CashBookEntry, BankAccount
from apps.finance.models.enums import CashEntryCategory, CashEntryType


def csv_response(filename: str, headers: list, rows: list) -> HttpResponse:
    """Build a downloadable CSV from headers + list-of-lists rows."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


class ReportService:
    @staticmethod
    def _billing_income_total(from_date, to_date) -> Decimal:
        """Authoritative billing income: line income on active invoices billed
        in range, across every payment mode (cash / UPI / card / bank /
        customer wallet). This is the P&L income source — pass-through money
        (the difference between a line's ``amount`` and ``income_amount``) is
        deliberately excluded.
        """
        return (
            InvoiceLine.objects.filter(
                invoice__is_active=True,
                invoice__billed_on__gte=from_date,
                invoice__billed_on__lte=to_date,
            ).aggregate(total=Coalesce(Sum("income_amount"), Decimal("0")))["total"]
            or Decimal("0")
        )

    @staticmethod
    def _linked_cash_entry_ids() -> set:
        """Cash Book income entry ids that billing created (so the P&L counts
        them once, through ``InvoiceLine.income_amount``, instead of again
        through the cash book)."""
        ids = set()
        ids.update(Invoice.objects.exclude(cash_entry_id=None).values_list("cash_entry_id", flat=True))
        ids.update(InvoicePayment.objects.exclude(cash_entry_id=None).values_list("cash_entry_id", flat=True))
        ids.update(InvoiceLine.objects.exclude(cash_entry_id=None).values_list("cash_entry_id", flat=True))
        return ids

    @staticmethod
    def _income_expense_breakdown(from_date, to_date):
        entries = CashBookEntry.objects.filter(entry_date__gte=from_date, entry_date__lte=to_date)
        linked = ReportService._linked_cash_entry_ids()
        income_qs = entries.filter(entry_type=CashEntryType.INCOME).exclude(category=CashEntryCategory.OWNER_DEPOSIT)
        if linked:
            income_qs = income_qs.exclude(id__in=linked)
        income_rows = list(
            income_qs.values("category")
            .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
            .order_by("-total")
        )
        billing_income = ReportService._billing_income_total(from_date, to_date)
        if billing_income:
            income_rows.insert(0, {"category": "Billing income (all modes)", "total": billing_income})
        expense_rows = (
            entries.filter(entry_type=CashEntryType.EXPENSE)
            .exclude(category__in=[CashEntryCategory.OWNER_WITHDRAWAL, CashEntryCategory.ADVANCE])
            .values("category")
            .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
            .order_by("-total")
        )
        return income_rows, expense_rows

    @staticmethod
    def income_total(from_date, to_date) -> Decimal:
        """Total income for a date range (billing income + non-billing cash
        book income). Used by the dashboard's ``today_income`` stat."""
        income_rows, _ = ReportService._income_expense_breakdown(from_date, to_date)
        return sum(Decimal(row["total"]) for row in income_rows)

    @staticmethod
    def profit_loss(from_date, to_date):
        income_rows, expense_rows = ReportService._income_expense_breakdown(from_date, to_date)
        income_total = sum(Decimal(row["total"]) for row in income_rows)
        cash_out_total = sum(
            Decimal(row["total"]) for row in expense_rows if row["category"] == CashEntryCategory.CASH_OUT
        )
        operating_expense_rows = [
            row for row in expense_rows if row["category"] != CashEntryCategory.CASH_OUT
        ]
        operating_expense_total = sum(Decimal(row["total"]) for row in operating_expense_rows)
        net = income_total - operating_expense_total
        margin = None
        if income_total > 0:
            margin = round((net / income_total) * 100, 2)
        return {
            "income": income_rows,
            "income_total": income_total,
            "expense": operating_expense_rows,
            "expense_total": operating_expense_total,
            "cash_out_total": cash_out_total,
            "net": net,
            "margin": margin,
        }

    @staticmethod
    def profit_loss_csv(data, from_date, to_date):
        rows = []
        for row in data["income"]:
            rows.append(["Income", row["category"], "", row["total"]])
        for row in data["expense"]:
            rows.append(["Expense", row["category"], "", row["total"]])
        rows.append(["Cash out (principal)", "CASH_OUT", "", data["cash_out_total"]])
        rows.append(["NET PROFIT", "", "", data["net"]])
        return csv_response(
            f"profit-loss-{from_date}-{to_date}.csv",
            ["Type", "Category", "Detail", "Amount"],
            rows,
        )

    @staticmethod
    def bank_statement(account: BankAccount, from_date, to_date):
        before = (
            account.transactions.filter(entry_date__lt=from_date)
            .aggregate(
                net=Coalesce(
                    Sum(
                        Case(
                            When(transaction_type="CREDIT", then=F("amount")),
                            default=-F("amount"),
                        )
                    ),
                    Decimal("0"),
                )
            )["net"]
        )
        opening = account.opening_balance + before
        txns = (
            account.transactions.filter(entry_date__gte=from_date, entry_date__lte=to_date)
            .order_by("entry_date", "created_at")
        )
        rows = [
            {
                "entry_date": txn.entry_date,
                "reference": txn.reference_number,
                "type": txn.transaction_type,
                "category": txn.category,
                "party": txn.party_name,
                "description": txn.description,
                "amount": txn.amount,
                "balance_after": txn.balance_after,
            }
            for txn in txns
        ]
        closing = opening + sum(
            Decimal(r["amount"]) if r["type"] == "CREDIT" else -Decimal(r["amount"]) for r in rows
        )
        return {"rows": rows, "opening": opening, "closing": closing}

    @staticmethod
    def bank_statement_csv(data, account_name, from_date, to_date):
        rows = [[str(r["entry_date"]), r["reference"], r["type"], r["category"], r["party"], r["amount"], r["balance_after"]] for r in data["rows"]]
        rows.append(["", "", "", "", "Opening balance", "", data["opening"]])
        rows.append(["", "", "", "", "Closing balance", "", data["closing"]])
        return csv_response(
            f"bank-statement-{account_name}-{from_date}-{to_date}.csv",
            ["Date", "Reference", "Type", "Category", "Party", "Amount", "Balance"],
            rows,
        )

    @staticmethod
    def customer_ledger(from_date, to_date, customer_id=None):
        invoices = Invoice.objects.filter(billed_on__gte=from_date, billed_on__lte=to_date)
        if customer_id:
            invoices = invoices.filter(customer_id=customer_id)
        invoices = invoices.select_related("customer").order_by("customer__full_name", "billed_on")
        rows = []
        totals = {"billed": Decimal("0"), "paid": Decimal("0"), "outstanding": Decimal("0")}
        for invoice in invoices:
            paid = invoice.paid_amount
            outstanding = invoice.outstanding_amount
            totals["billed"] += invoice.total
            totals["paid"] += paid
            totals["outstanding"] += outstanding
            rows.append(
                {
                    "customer": invoice.customer.full_name if invoice.customer else "Walk-in",
                    "invoice": invoice.invoice_number,
                    "date": invoice.billed_on,
                    "total": invoice.total,
                    "paid": paid,
                    "outstanding": outstanding,
                }
            )
        return {"rows": rows, "totals": totals}

    @staticmethod
    def customer_ledger_csv(data, from_date, to_date):
        rows = [[r["customer"], r["invoice"], str(r["date"]), r["total"], r["paid"], r["outstanding"]] for r in data["rows"]]
        rows.append(["", "", "TOTAL", data["totals"]["billed"], data["totals"]["paid"], data["totals"]["outstanding"]])
        return csv_response(
            f"customer-ledger-{from_date}-{to_date}.csv",
            ["Customer", "Invoice", "Date", "Billed", "Paid", "Outstanding"],
            rows,
        )

    @staticmethod
    def wallet_statement(employee: Employee, from_date, to_date):
        wallet = getattr(employee, "wallet", None)
        before = Decimal("0")
        if wallet is not None:
            before = (
                wallet.transactions.filter(entry_date__lt=from_date)
                .aggregate(
                    net=Coalesce(
                        Sum(
                            Case(
                                When(transaction_type="CREDIT", then=F("amount")),
                                default=-F("amount"),
                            )
                        ),
                        Decimal("0"),
                    )
                )["net"]
            )
            txns = wallet.transactions.filter(
                entry_date__gte=from_date, entry_date__lte=to_date
            ).order_by("entry_date", "created_at")
        else:
            txns = WalletTransaction.objects.none()
        rows = [
            {
                "entry_date": txn.entry_date,
                "reference": txn.reference_number,
                "type": txn.transaction_type,
                "category": txn.category,
                "source": txn.source,
                "destination": txn.destination,
                "amount": txn.amount,
                "balance_after": txn.balance_after,
            }
            for txn in txns
        ]
        closing = before + sum(
            Decimal(r["amount"]) if r["type"] == "CREDIT" else -Decimal(r["amount"]) for r in rows
        )
        return {"rows": rows, "opening": before, "closing": closing}

    @staticmethod
    def wallet_statement_csv(data, employee_name, from_date, to_date):
        rows = [[str(r["entry_date"]), r["reference"], r["type"], r["category"], r["source"], r["destination"], r["amount"], r["balance_after"]] for r in data["rows"]]
        rows.append(["", "", "", "", "", "", "Opening balance", data["opening"]])
        rows.append(["", "", "", "", "", "", "Closing balance", data["closing"]])
        return csv_response(
            f"wallet-statement-{employee_name}-{from_date}-{to_date}.csv",
            ["Date", "Reference", "Type", "Category", "Source", "Destination", "Amount", "Balance"],
            rows,
        )

    @staticmethod
    def salary_summary(from_date, to_date):
        entries = (
            WorkLogEntry.objects.filter(
                status=WorkLogStatus.APPROVED, work_date__gte=from_date, work_date__lte=to_date
            )
            .values("employee__id", "employee__full_name")
            .annotate(
                entries=Count("id"),
                hours=Coalesce(Sum("hours_worked"), Decimal("0")),
                wage=Coalesce(Sum("wage_amount"), Decimal("0")),
            )
            .order_by("-wage")
        )
        total_wage = sum(Decimal(row["wage"]) for row in entries)
        return {"rows": entries, "total_wage": total_wage}

    @staticmethod
    def salary_summary_csv(data, from_date, to_date):
        rows = [[r["employee__full_name"], r["entries"], r["hours"], r["wage"]] for r in data["rows"]]
        rows.append(["TOTAL", "", "", data["total_wage"]])
        return csv_response(
            f"salary-summary-{from_date}-{to_date}.csv",
            ["Employee", "Entries", "Hours", "Wage"],
            rows,
        )

    @staticmethod
    def analytics(from_date, to_date):
        invoices = Invoice.objects.filter(billed_on__gte=from_date, billed_on__lte=to_date)
        peak_hours = (
            invoices.annotate(hour=TruncHour("created_at"))
            .values("hour")
            .annotate(count=Count("id"), revenue=Coalesce(Sum("total"), Decimal("0")))
            .order_by("-count")
        )
        top_services = (
            InvoiceLine.objects.filter(invoice__billed_on__gte=from_date, invoice__billed_on__lte=to_date)
            .values("description")
            .annotate(
                qty=Coalesce(Sum("qty"), Decimal("0")),
                revenue=Coalesce(Sum("amount"), Decimal("0")),
            )
            .order_by("-revenue")
        )
        per_employee = (
            invoices.values("created_by__username", "created_by__first_name")
            .annotate(count=Count("id"), revenue=Coalesce(Sum("total"), Decimal("0")))
            .order_by("-revenue")
        )
        return {
            "peak_hours": peak_hours,
            "top_services": top_services,
            "per_employee": per_employee,
        }
