# AK NAZAR CYBER CAFE ERP — Project Status

> **Purpose of this file:** a single source of truth so any future session
> (or the owner returning to the project) can resume exactly where work
> stopped. Read this first, then the README.

---

## 1. What this project is

Production-grade ERP for AK Nazar Cyber Cafe and its branches. Built on
Django 5.2 / Python 3.11. Combines CRM, Billing, Accounting, Employee
Management, Inventory, Customer Management, Wallet Engine, Cash Book,
Bank Ledger, Reporting and Audit.

Core philosophy: **every rupee must be traceable** (source, destination,
reference, responsible employee, timestamp). Money is always `Decimal`.
Balances are derived from ledger transactions, never stored. Soft delete
is the only delete. Business logic lives in services, queries in
selectors, views stay thin.

---

## 2. Current status (as of last session)

| Sprint | Deliverables | Status |
|--------|--------------|--------|
| 1 | Foundation, Auth, Roles, Permissions, Employees, Base Layout | Done |
| 2 | Wallet Engine, Cash Book, Bank Ledger | Done |
| 3 | Customers, Services, Daily Work Log | **Done** (committed) |
| 4 | Billing, Dashboard, Reports, Analytics | **Done** (this session) |
| 5 | Inventory | Next |

Tests: full suite passes. Ruff lint clean. All migrations applied.

### Sprint 4 deliverables (built this session)
1. **Billing** (`apps/billing/`) — `Invoice`, `InvoiceLine` (service, qty,
   snapshot price), `InvoicePayment` (partial/full settlements),
   `CashOut` (E-Sathi). `BillingService.create_invoice` mints `INV-xxxxxx`,
   validates credit limit, auto-books Cash Book income for non-credit
   payments; `settle_invoice` (partial/full → UNPAID/PARTIAL/PAID) and
   `soft_delete_invoice` (voids linked Cash Book entries) complete the API.
   `CashOutService.create_cash_out` atomically books bank deposit
   (`PAYMENT_RECEIVED`), COMMISSION income and CASH_OUT expense.
2. **Reference prefixes** — `ReferenceService` now mints `INV` (invoice)
   and `COUT` (cash-out) references.
3. **Cash categories** — `apps/finance/models/enums.py` gained
   `COMMISSION` (income) + `CASH_OUT` (expense); migration `finance.0002`.
4. **Reports** (`apps/reports/`) — date-range P&L, bank statement
   (opening/closing balance), customer ledger, wallet statement, salary
   summary (approved work-log wages), analytics (today/billing totals,
   payment-mode split, top services, recent cash-outs, per-status invoice
   counts). Every report has a CSV download button.
5. **Dashboard upgrades** — today's billing, pending invoices, outstanding
   receivables, top services cards + New Bill / Cash Out quick actions.
6. **Roles** — `seed_roles` matrix extended (Owner/Manager full;
   Accountant manages finance + billing; Cashier/Counter Staff create
   billing; Staff view-only).
7. Wired: `INSTALLED_APPS`, root URLs (`/billing/`, `/reports/`), sidebar
   (Billing, Reports enabled), migrations `billing.0001` applied. New-app
   test run green (40 tests) before full-suite re-run.

### Sprint 3 deliverables (built last session)
1. **Customers** (`apps/customers/`) — profiles only (decision: wallets stay
   employee-only). `Customer` model (full_name, phone unique, email,
   address, `credit_limit`), `CustomerService` (create/update/deactivate/
   restore with phone-uniqueness + non-negative credit limit rules),
   `CustomerSelector`, `CustomerForm`, list/detail/update/deactivate views,
   admin, list/create-on-one-page UI, templates.
2. **Services** (`apps/services/`) — `Service` (name unique, category enum,
   unit, price), `ServicePriceHistory` (append-only). `ServiceService`
   mints the opening price row on create and appends a history row whenever
   the price changes. List + detail (edit + price history) views, admin.
3. **Daily Work Log** (in `apps/employees`) — `WorkLogEntry` (employee,
   work_date, times, `hours_worked`, `rate_applied` snapshot, status,
   `approved_by`/`approved_at`). `Employee.hourly_rate` added (migration
   `employees.0003`). `WorkLogService.create_entry` derives hours from
   start/end when given and snapshots the rate; **`approve_entry` credits
   the employee's wallet as SALARY atomically**; `reject_entry` does not.
   Work log list page (create + filter + approve/reject POST actions).
4. Wired: `INSTALLED_APPS`, root URLs (`/customers/`, `/services/`,
   `/employees/worklogs/`), sidebar (Customers, Services, Daily Work Log
   enabled), dashboard stats (customers, services, pending work logs),
   `seed_roles` matrix (Accountant: finance manage, new modules view-only).

---

## 3. Architecture & conventions (must follow)

- Every model inherits `apps.common.models.BaseModel`:
  UUID pk, `created_at/updated_at/created_by/updated_by`,
  `deleted_at/deleted_by`, `is_active`, `soft_delete()`. Never duplicate
  these fields. Never hard delete.
- **Folder structure per app:** `models/`, `views/`, `services/`,
  `selectors/`, `forms/`, `urls.py`, `admin.py`, `apps.py`, `tests/`.
- **Service layer:** business rules in `services/` (validations, atomic
  transactions, reference minting). Views call services only.
- **Selector layer:** ORM queries live in `selectors/`; templates never
  query.
- **Triple validation:** model + form + service.
- **Reference numbers:** minted via
  `apps.common.services.reference_service.ReferenceService` —
  `WAL-xxxxxx` (wallet), `CB-xxxxxx` (cash book), `BANK-xxxxxx` (bank),
  `INV-xxxxxx` (invoice), `COUT-xxxxxx` (cash-out).
  Non-financial records (customers, services) don't need references.
- **Money:** `Decimal`, `MONEY_MAX_DIGITS=18`, `MONEY_DECIMAL_PLACES=2`
  in `config/settings/base.py` via the `money_field()` helper. Use the
  `inr` template filter. **`by=` parameters always receive a `User`, never
  an `Employee`** (audit FKs point at `accounts.User`).
- **Roles = Django Groups.** `manage.py seed_roles` is idempotent.
  Views gate with `PermissionRequiredMixin`.
- **Audit fields** auto-fill via `CurrentUserMiddleware` + `BaseModel.save`.
- **Lint:** `ruff check apps config manage.py` · **Tests:**
  `python3 manage.py test` (runs as superuser/seeded groups in setUp).

---

## 4. What is built (modules map)

| Module | App | Models | Key entry points |
|--------|-----|--------|------------------|
| Common base | `apps.common` | `BaseModel`, managers, middleware, tags | admin.py, templatetags/erp_tags.py |
| Auth | `apps.accounts` | `User` (AbstractBaseUser), throttling | `/accounts/`, owner_bootstrap_service |
| Employees | `apps.employees` | `Employee`, `Wallet`, `WalletTransaction`, `WorkLogEntry` | `/employees/`, `/employees/wallets/`, `/employees/worklogs/` |
| Finance | `apps.finance` | `CashBookEntry`, `BankAccount`, `BankTransaction` | `/finance/cashbook/`, `/finance/bank/` |
| Customers | `apps.customers` | `Customer` | `/customers/` |
| Services | `apps.services` | `Service`, `ServicePriceHistory` | `/services/` |
| Billing | `apps.billing` | `Invoice`, `InvoiceLine`, `InvoicePayment`, `CashOut` | `/billing/`, `/billing/cashout/` |
| Reports | `apps.reports` | (service layer, no models) | `/reports/` + CSV |
| Pages | `apps.pages` | Dashboard | `/` |

Wallet service API (`apps/employees/services/wallet_service.py`):
`credit`, `debit`, `transfer`, `balance_of`, `get_or_create_wallet`.
Every employee gets a wallet at creation (`employee_service.py`).

Work log API (`apps/employees/services/worklog_service.py`):
`create_entry`, `approve_entry` (auto SALARY credit), `reject_entry`.

Finance services: `CashBookService.record_income/record_expense/balance/
day_balance/soft_delete_entry`; `BankService.create_account/deposit/
withdraw/transfer/balance_of`.

Customer service: `CustomerService.create_customer/update_customer/
deactivate_customer/restore_customer`.
Service catalog: `ServiceService.create_service/update_service/
deactivate_service/restore_service` (price changes append history).

Billing API (`apps/billing/services/billing_service.py`):
`BillingService.create_invoice/settle_invoice/soft_delete_invoice`;
`CashOutService.create_cash_out` (bank deposit + COMMISSION income +
CASH_OUT expense atomically). Invoice totals are always derived from
lines; credit is enforced against `Customer.credit_limit` via
`InvoiceSelector.outstanding_for_customer`.

Report API (`apps/reports/services/report_service.py`): `profit_loss`,
`bank_statement`, `customer_ledger`, `wallet_statement`, `salary_summary`,
`analytics`, `csv_response`.

---

## 5. Known technical debt / deferred items

- Finance view tests still live in `apps/employees/tests/test_wallet_views.py`
  (misnamed file) — tidy later; same applies to the newer per-app tests.
- `db.sqlite3` is committed in the repo. For production switch to
  PostgreSQL (settings `config.settings.production`).
- Wallet / bank balances are derived by SUM over all transactions; large
  ledgers may need indexed range queries or caching as data grows.
- Cash-out (`CashOut`) soft delete intentionally leaves ledger entries
  behind (voiding money movement is irreversible and recorded as debt).
  Void is not offered for cash-outs in the UI.
- Daily Work Log: no duplicate-shift guard per employee+day (multiple
  entries allowed); wage is snapshot-based, no attendance clocking.
- Printing/colour/online-form-fill billing is catalog `Service` line
  items — no dedicated billing code, by design.

---

## 6. Next steps (Sprint 5 — Inventory)

Planned scope:
1. **Inventory** (`apps/inventory/`): stock items/consumables, units,
   stock-in / stock-out (issue to cafe terminals), low-stock alerts,
   stock valuation, reconciliation against usage.
2. **Purchase ledger** if needed (supplier + purchases vs cash book).
3. Possible hardening: performance indexes on ledger tables, dashboard
   caching, invoice printing (A4/POS) template.

Recommended order: models → services/selectors → views/forms/templates →
seed_roles matrix + tests, then full `ruff check` + test run before
committing.

---

## 7. How to run

```bash
# Dependencies (already installed in this environment)
pip install --break-system-packages -r requirements.txt

# First time only
cp .env.example .env
python3 manage.py migrate
python3 manage.py seed_roles
python3 manage.py createsuperuser

# Run
python3 manage.py runserver
```

Quality gates before every commit:
```bash
ruff check apps config manage.py
python3 manage.py test
```

---

## 8. Project guidelines (brief reminder)

Read the full plan in `readme.txt` / previous conversation context.
Key rules: never hard delete, never mutate balances directly (always
transactions), never put business logic in views, never query in
templates, always follow sprint order, always ASK when unsure.
