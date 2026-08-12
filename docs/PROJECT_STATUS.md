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
8. **Operational fix (follow-up)**: the committed `db.sqlite3` carried stale
   role permissions (seed_roles had only been re-run in test DBs). Staff
   login hit 403s on Customers / Services / Daily Work Log / Billing until
   `python3 manage.py seed_roles` was re-run against the live DB. All
   groups now match the matrix; debug test accounts were removed from the
   committed DB.

### Sprint 4 follow-up — service categories + custom fields (this session)
1. **Free-form categories** — `Service.category` is now a FK to the new
   `services.Category` model instead of a fixed choice list. Defaults
   (Games, Internet, Printing, Recharge, Snacks, Other) are seeded and
   every existing service was mapped over (migration `services.0003`).
   The service form has a **"New category"** input: pick an existing one
   or type a brand-new one — the "Other / define your own" flow.
2. **Custom fields per service** — `services.ServiceCustomField`
   (label, type, required, help_text, ordering, `roles`). Types: TEXT,
   NUMBER, PERCENT, DATE, **BANK_ACCOUNT**, **BANK_TRANSFER
   (auto-deposit)**. Created/edited/removed by the **Owner only**
   (custom-field manage perms are excluded from every other role in
   `seed_roles`); staff can see the definitions.
3. **Role-based field permissions** — each field lists the role codes that
   may see/fill it (blank = everyone). Owner sets them in the add-field
   form. `ServiceSelector.visible_custom_fields()` applies the rule, and
   `BillingService` rejects any value for a field the billing user's role
   is not allowed to fill.
4. **Billing integration** — the billing screen fetches a service's fields
   (JSON endpoint `/services/custom-fields-json/`) and renders them
   dynamically per line. Values are validated + snapshotted into
   `billing.InvoiceLineFieldValue` (label/type snapshot, so past bills stay
   readable) and shown on the invoice detail page. A `BANK_TRANSFER`
   amount paired with a `BANK_ACCOUNT` books a real bank deposit
   (`PAYMENT_RECEIVED`) into the selected account atomically with the
   invoice.
5. **Example (Cash Withdrawal)**: owner adds the service under category
   "Cash Withdrawal", then defines fields — "Amount given" (NUMBER),
   "Commission %" (PERCENT, manager-only), "Customer transferred"
   (BANK_TRANSFER), "Bank account" (BANK_ACCOUNT). When counter staff
   bill it, the transfer is auto-deposited into the chosen bank account
   and every value appears on the bill.
6. Tests: +18 new service/billing tests (categories, custom-field CRUD,
   role gating, required/type validation, auto-deposit, permission 403s,
   JSON endpoint, category filter).

### Sprint 4 follow-up (Phase 1) — expense add + per-staff cash book + quick customer (this session)
The owner's requested feature list (billing add-on items, expense entry,
cash book rework) started landing here:
1. **Expense add with mode + staff** — a manual expense entry now carries
   the responsible staff member. `CashBookEntry.staff` (FK, soft) is set
   automatically from the logged-in user's employee profile (or passed
   explicitly to the service). Every expense shows up in that staff's own
   cash book, so "kis staff ne kya kharcha kiya" is answerable per staff.
2. **Per-staff cash books + shop combined view** — the Cash Book page is
   now scoped. Staff / cashier / counter users see **only their own
   entries**; Owner / Manager / Accountant see the whole shop and can
   filter by any staff member from a dropdown. All summary numbers
   (balance, in, out, today, as-on-date) follow the selected scope.
3. **Today + balance-as-on-date cards** — new summary strip shows Today
   In / Today Out / Today Balance, an "as on <date>" balance picker
   (`?as_on=YYYY-MM-DD`), and all-time totals. Auto income from billing
   still feeds the book through `CashBookService.record_income`.
4. **Owner Withdrawal / Deposit** — dedicated Owner Cash card (permission
   `finance.withdraw_shop_cash`, Owner/Manager/Accountant only). Withdraw
   books `OWNER_WITHDRAWAL` (expense), deposit books `OWNER_DEPOSIT`
   (income) — the owner's money movements are traceable in the ledger.
5. **Income-only / expense-only permission split** — manual cash book
   entry rights are now granular: `add_cashbookincome` /
   `add_cashbookexpense`. Cashier & Counter Staff can record income only;
   Staff get none; Owner/Manager/Accountant can record both. The form only
   shows the entry types the user is allowed to save.
6. **Quick customer add on billing** — the billing screen has a "Customer
   name (new)" field. If the user has `customers.add_customer`, a checkbox
   saves it as a real `Customer` row and links the invoice. Without the
   permission the name is still kept as a snapshot on the invoice
   (`Invoice.customer_name`), so walk-in bills carry the customer's name
   and are searchable — no DB customer record is created. Credit bills
   still require a registered customer.
7. **Permissions & roles** — `seed_roles` updated (Owner 67 / Manager 64 /
   Accountant 46 / Cashier 21 / Counter Staff 21 / Staff 16) with the new
   cash book custom permissions; re-run against the live DB.
8. Tests: +29 new Phase-1 tests (per-staff scoping, owner cash, permission
   gating, quick customer creation/name-snapshot/403 handling, form type
   restriction, staff-scoped as-on balance).

### Sprint 4 follow-up (Phase 2) — 2-wallet model + split-payment billing (this session)
The owner's 2-wallet example (1000 cash given / 1040 UPI paid / 40 charge)
now works end-to-end through the billing screen:

1. **Two wallets per staff** — each employee has a CASH and an ONLINE/UPI
   wallet (`Wallet.wallet_type`, unique per employee+type). Owner top-up
   mirrors into the shop ledgers: CASH float books a cash-book `ADVANCE`
   expense, ONLINE float books a bank withdrawal — staff floats stay
   traceable shop-side. (Replaces the earlier 1-wallet-with-category idea.)
2. **Split-payment billing** — the New Bill card now has a Split Payment
   section: repeatable cash / UPI / card / bank rows, each with an amount
   and (for non-cash) a shop bank account. Amounts must sum to the bill
   total; blank rows are ignored; a partial sum flips the invoice to
   PARTIAL (requires a customer), a zero sum to credit/UNPAID.
3. **Per-leg auto-ledger** — every payment books atomically with the
   invoice: cash legs book Cash Book `SALES` income + credit the billing
   staff's CASH wallet; UPI/bank legs deposit `PAYMENT_RECEIVED` into the
   chosen bank account + credit the staff's ONLINE wallet. Each leg is
   linked (`InvoicePayment.cash_entry` / `.bank_transaction`) so a void
   reverses both ledgers.
4. **Cash-withdrawal line auto-ledger** — a line whose custom fields include
   a `BANK_TRANSFER` + `BANK_ACCOUNT` pair (and optional `PERCENT`
   commission) becomes a withdrawal line. Its amount becomes the transfer
   value (e.g. `1000 + 4% = 1040`), the billing staff's CASH wallet is
   debited the cash handed out, `COMMISSION` income and the `CASH_OUT`
   expense hit the Cash Book, and the UPI payment (bank account defaults to
   the withdrawal line's) covers the bank side. The bill detail shows the
   breakdown (e.g. `1000 + 4% = 1040`) under the line.
5. **UI** — wallet list shows Cash + Online columns per employee; wallet
   detail has an Owner Top-up tab (bank account required for ONLINE);
   invoice detail lists each payment with its bank/UPI account.
6. Tests: wallet service/views updated for the FK wallet model; new split
   payment + withdrawal auto-ledger tests (full scenario, partial/credit
   rules, void reversal of bank deposits). Full suite green.

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
- **P&L currently reads only the Cash Book.** Since UPI/bank sales now
  deposit into the bank ledger (not the cash book), the Profit & Loss
  report under-states income from UPI/card/bank payments and from
  withdrawal transfer-in. Recommended follow-up: fold bank `PAYMENT_RECEIVED`
  into P&L income while excluding withdrawal/cash-out principal (the
  commission entry already carries the P&L income for those), and mirror
  staff ONLINE-float top-ups as bank expense.
- `settle_invoice` still books settlements into the Cash Book only (no
  staff-wallet credit / bank deposit for UPI settlements). Full split
  settlements were left out of scope this session; the create-bill path
  carries the wallet + bank auto-ledger.

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
