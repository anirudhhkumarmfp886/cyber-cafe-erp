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
| 4 | Billing, Dashboard, Reports, Analytics | **Next** |

Tests: full suite passes. Ruff lint clean. All migrations applied.

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
  `WAL-xxxxxx` (wallet), `CB-xxxxxx` (cash book), `BANK-xxxxxx` (bank).
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

---

## 5. Known technical debt / deferred items

- Finance view tests still live in `apps/employees/tests/test_wallet_views.py`
  (misnamed file) — tidy later; same applies to the newer per-app tests.
- `db.sqlite3` is committed in the repo. For production switch to
  PostgreSQL (settings `config.settings.production`).
- Wallet / bank balances are derived by SUM over all transactions; large
  ledgers may need indexed range queries or caching in Sprint 4 reporting.
- Customers have no wallet / receivable ledger yet (decision in Sprint 3).
  Sprint 4 billing must model customer invoices and how they settle
  (cash / UPI / against credit limit) — reconcile against Cash Book.
- Daily Work Log: no duplicate-shift guard per employee+day (multiple
  entries allowed); wage is snapshot-based, no attendance clocking.

---

## 6. Next steps (Sprint 4 — Billing, Dashboard, Reports, Analytics)

Planned scope:
1. **Billing** (`apps/billing/`): customer sessions/invoices, bill lines
   (service x qty x price, using `ServicePriceHistory`), payment modes,
   settlement against cash book / credit limit, invoice reference numbers
   (`INV-xxxxxx`), soft delete. Money rules: totals derived from lines.
2. **Dashboard upgrades**: today's sales, top services, pending invoices,
   staff wallet liabilities vs cash book.
3. **Reports** (`apps/reports/` or in finance): date-range P&L summary,
   bank statement export, customer ledger, wallet statement, work-log
   salary summary. CSV export for each.
4. **Analytics**: peak hours, service popularity, per-employee sales.

Recommended order: Billing models/services → billing views/forms/templates →
dashboard stats → reports/CSV → seed_roles matrix + tests, then full
`ruff check` + test run before committing.

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
