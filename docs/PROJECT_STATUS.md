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
| 2 | Wallet Engine, Cash Book, Bank Ledger | **Done** (cleanup committed) |
| 3 | Customers, Services, Daily Work Log | **Next** |
| 4 | Billing, Dashboard, Reports, Analytics | Planned |

Tests: full suite passes (details below). Ruff lint clean. All migrations
applied (SQLite dev DB).

### Sprint 2 cleanup completed in the last session
1. Fixed `templates/finance/bank_detail.html` — statement used
   `txn.txn_type` (nonexistent attribute), so Credit/Debit columns never
   rendered and badges were always red. Now uses `txn.is_credit`.
2. Fixed `apps/employees/management/commands/seed_roles.py` — Accountant
   now matches the documented matrix: Employee = view-only, Wallet / Cash
   Book / Bank = manage. (Previously `managed=True` granted add/change/
   delete on every model including Employee.) Refactored to a
   `_permissions_for(managed_models)` helper.
3. Registered `Wallet` and `WalletTransaction` in Django admin
   (`apps/employees/admin.py`) for auditability.
4. Added `test_bank_detail_statement_renders_credit_and_debit_columns` in
   `apps/employees/tests/test_wallet_views.py` to lock in fix #1.
5. Updated `README.md` status to Sprint 2 complete.

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
- **Money:** `Decimal`, `MONEY_MAX_DIGITS=18`, `MONEY_DECIMAL_PLACES=2`
  in `config/settings/base.py`. Use the `inr` template filter.
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
| Employees | `apps.employees` | `Employee`, `Wallet`, `WalletTransaction` | `/employees/`, `/employees/wallets/` |
| Finance | `apps.finance` | `CashBookEntry`, `BankAccount`, `BankTransaction` | `/finance/cashbook/`, `/finance/bank/` |
| Pages | `apps.pages` | Dashboard | `/` |

Wallet service API (`apps/employees/services/wallet_service.py`):
`credit`, `debit`, `transfer`, `balance_of`, `get_or_create_wallet`.
Every employee gets a wallet at creation (`employee_service.py:105`).

Finance services: `CashBookService.record_income/record_expense/balance/
day_balance/soft_delete_entry`; `BankService.create_account/deposit/
withdraw/transfer/balance_of`.

---

## 5. Known technical debt / deferred items

- Finance view tests still live in `apps/employees/tests/test_wallet_views.py`
  (misnamed file) — no functional impact, tidy later.
- `db.sqlite3` is committed in the repo. For production switch to
  PostgreSQL (settings `config.settings.production`).
- Wallet balance / bank balance are derived by SUM over all transactions;
  with large ledgers this may need indexed range queries or caching in a
  later sprint (Sprint 4 reporting).
- No customer/session/billing models yet — that is Sprint 3+.

---

## 6. Next steps (Sprint 3 — Customers, Services, Daily Work Log)

Planned scope:
1. **Customers app** (`apps/customers/`): customer profile (name, contact,
   wallet balance tie-in, credit limits), soft delete, service layer,
   selectors, admin.
2. **Services app** (`apps/services/` or inside cafe module): catalog of
   billable services (game rates, printing, internet packages), pricing
   history, active flag.
3. **Daily Work Log** (`apps/attendance/` or in employees): per-employee
   shift/work-log entries, supervisor approval, linkage to wages/wallet.

Recommended order: Customers → Services → Daily Work Log, each with
`models/services/selectors/forms/views/urls/admin/tests`, followed by a
full `ruff check` + test run.

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
