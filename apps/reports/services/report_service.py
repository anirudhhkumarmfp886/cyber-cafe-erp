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
from apps.employees.models import (
    Employee,
    WalletTransaction,
    WalletTransactionCategory,
    WalletTransactionType,
    WorkLogEntry,
    WorkLogStatus,
)
from apps.finance.models import BankAccount, CashBookEntry
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
    @staticmethod
    def _billing_income_breakdown(from_date, to_date):
        """Calculates both Realized (Cash-Collected) Billing Income and Total Billed Income.

        Realized Income = sum of max(0, inv.paid_amount - inv.pass_through_amount)
        Total Billed Income = sum of inv.income_amount
        Due/Uncollected Income = Total Billed - Realized
        """
        invoices = (
            Invoice.objects.filter(
                is_active=True,
                billed_on__gte=from_date,
                billed_on__lte=to_date,
            )
            .prefetch_related("lines", "payments")
        )
        total_billed_income = Decimal("0")
        realized_income = Decimal("0")

        for inv in invoices:
            total_billed_income += inv.income_amount
            # Realized income is whatever paid amount exceeds pass-through cost (capped at line income)
            realized = min(inv.income_amount, max(Decimal("0"), inv.paid_amount - inv.pass_through_amount))
            realized_income += realized

        uncollected_due_income = max(Decimal("0"), total_billed_income - realized_income)
        return {
            "total_billed_income": total_billed_income,
            "realized_income": realized_income,
            "uncollected_due_income": uncollected_due_income,
        }

    @staticmethod
    def _billing_income_total(from_date, to_date) -> Decimal:
        """Realized billing income collected in date range."""
        return ReportService._billing_income_breakdown(from_date, to_date)["realized_income"]

    @staticmethod
    def _linked_cash_entry_ids() -> set:
        """Cash Book income entry ids that billing created (so the P&L counts
        them once, through billing income, instead of again
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
        income_qs = entries.filter(entry_type=CashEntryType.INCOME).exclude(
            category__in=[CashEntryCategory.OWNER_DEPOSIT, CashEntryCategory.FLOAT_IN]
        )
        if linked:
            income_qs = income_qs.exclude(id__in=linked)
        income_rows = list(
            income_qs.values("category")
            .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
            .order_by("-total")
        )
        billing_stats = ReportService._billing_income_breakdown(from_date, to_date)
        realized_billing = billing_stats["realized_income"]
        if realized_billing:
            income_rows.insert(0, {"category": "Billing income (all modes)", "total": realized_billing})
        # 1. Drawer Expenses
        drawer_expenses = entries.filter(entry_type=CashEntryType.EXPENSE).exclude(
            category__in=[
                CashEntryCategory.OWNER_WITHDRAWAL,
                CashEntryCategory.ADVANCE,
                CashEntryCategory.FLOAT_OUT,
            ]
        )
        expense_by_cat = {}
        for row in drawer_expenses.values("category").annotate(total=Coalesce(Sum("amount"), Decimal("0"))):
            cat = row["category"]
            expense_by_cat[cat] = expense_by_cat.get(cat, Decimal("0")) + Decimal(str(row["total"]))

        # 2. Staff Float Expenses (from WalletTransaction)
        wallet_expenses = WalletTransaction.objects.filter(
            category=WalletTransactionCategory.EXPENSE,
            transaction_type=WalletTransactionType.DEBIT,
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
        )
        for w_txn in wallet_expenses:
            desc = w_txn.description or ""
            cat = "MISC"
            if "Counter float cash expense (" in desc:
                try:
                    cat = desc.split("Counter float cash expense (")[1].split(")")[0]
                except Exception:
                    cat = "MISC"
            expense_by_cat[cat] = expense_by_cat.get(cat, Decimal("0")) + Decimal(str(w_txn.amount))

        expense_rows = [
            {"category": cat, "total": amt}
            for cat, amt in sorted(expense_by_cat.items(), key=lambda x: x[1], reverse=True)
        ]
        return income_rows, expense_rows

    @staticmethod
    def staff_expense_breakdown(from_date, to_date):
        """Returns who spent how much in the given date range."""
        breakdown = {}
        # 1. From Cash Drawer
        drawer_entries = CashBookEntry.objects.filter(
            entry_date__gte=from_date,
            entry_date__lte=to_date,
            entry_type=CashEntryType.EXPENSE,
        ).exclude(
            category__in=[
                CashEntryCategory.OWNER_WITHDRAWAL,
                CashEntryCategory.ADVANCE,
                CashEntryCategory.FLOAT_OUT,
            ]
        ).select_related("staff")
        for entry in drawer_entries:
            name = entry.staff.full_name if entry.staff else "Shop Cash Drawer (Main Galla)"
            breakdown[name] = breakdown.get(name, Decimal("0")) + Decimal(str(entry.amount))

        # 2. From Staff Float Wallets
        wallet_expenses = WalletTransaction.objects.filter(
            category=WalletTransactionCategory.EXPENSE,
            transaction_type=WalletTransactionType.DEBIT,
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
        ).select_related("wallet__employee")
        for w_txn in wallet_expenses:
            name = w_txn.wallet.employee.full_name if w_txn.wallet and w_txn.wallet.employee else "Staff Float"
            breakdown[name] = breakdown.get(name, Decimal("0")) + Decimal(str(w_txn.amount))

        return [
            {"staff_name": name, "total": amt}
            for name, amt in sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
        ]

    @staticmethod
    def periodic_summary():
        """Returns Income, Expense, and Net Profit for Today, This Month, and This Year."""
        from datetime import date
        today = date.today()
        month_start = date(today.year, today.month, 1)
        year_start = date(today.year, 1, 1)

        today_pl = ReportService.profit_loss(today, today)
        month_pl = ReportService.profit_loss(month_start, today)
        year_pl = ReportService.profit_loss(year_start, today)

        return {
            "today": {
                "income": today_pl["income_total"],
                "expense": today_pl["expense_total"],
                "net": today_pl["net"],
                "margin": today_pl["margin"],
            },
            "this_month": {
                "income": month_pl["income_total"],
                "expense": month_pl["expense_total"],
                "net": month_pl["net"],
                "margin": month_pl["margin"],
            },
            "this_year": {
                "income": year_pl["income_total"],
                "expense": year_pl["expense_total"],
                "net": year_pl["net"],
                "margin": year_pl["margin"],
            },
        }

    @staticmethod
    def income_total(from_date, to_date) -> Decimal:
        """Total income for a date range (billing income + non-billing cash
        book income). Used by the dashboard's ``today_income`` stat."""
        income_rows, _ = ReportService._income_expense_breakdown(from_date, to_date)
        return sum(Decimal(row["total"]) for row in income_rows)

    @staticmethod
    def profit_loss(from_date, to_date):
        income_rows, expense_rows = ReportService._income_expense_breakdown(from_date, to_date)
        billing_stats = ReportService._billing_income_breakdown(from_date, to_date)
        due_income = billing_stats["uncollected_due_income"]
        
        income_total = sum(Decimal(row["total"]) for row in income_rows)
        billed_income_total = income_total + due_income

        cash_out_total = sum(
            Decimal(row["total"]) for row in expense_rows if row["category"] == CashEntryCategory.CASH_OUT
        )
        operating_expense_rows = [
            row for row in expense_rows if row["category"] != CashEntryCategory.CASH_OUT
        ]
        operating_expense_total = sum(Decimal(row["total"]) for row in operating_expense_rows)
        net = income_total - operating_expense_total
        net_billed = billed_income_total - operating_expense_total
        margin = None
        if income_total > 0:
            margin = round((net / income_total) * 100, 2)
        staff_expenses = ReportService.staff_expense_breakdown(from_date, to_date)
        return {
            "income": income_rows,
            "income_total": income_total,
            "billed_income_total": billed_income_total,
            "due_income": due_income,
            "expense": operating_expense_rows,
            "expense_total": operating_expense_total,
            "cash_out_total": cash_out_total,
            "net": net,
            "net_billed": net_billed,
            "margin": margin,
            "staff_expenses": staff_expenses,
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
