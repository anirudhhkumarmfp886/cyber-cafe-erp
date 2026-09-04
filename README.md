# AK NAZAR CYBER CAFE ERP

Production-grade ERP for AK Nazar Cyber Cafe and its branches.

An ERP platform that combines CRM, Billing, Accounting, Employee Management,
Inventory, Customer Management, Wallet Engine, Cash Book, Bank Ledger,
Reporting and Audit — built on Django.

> Status: **Sprint 6 (WhatsApp & Thermal Receipts) complete.** Billing now
> includes 1-click WhatsApp receipt sharing, 80mm thermal receipt printing,
> low-stock alerts with owner WhatsApp alerts, full inventory management with
> Weighted Average Cost (WAC), formula-driven pricing, and customer wallet.

---

## Tech Stack

| Layer        | Choice                                  |
|--------------|-----------------------------------------|
| Language     | Python 3.11                             |
| Framework    | Django 5.2                               |
| Database     | SQLite (dev) / PostgreSQL (production)   |
| Frontend     | Bootstrap 5.3 (CDN) + Bootstrap Icons    |
| Static       | Whitenoise (hashed manifests in prod)    |
| Quality      | Ruff lint, Django TestCase suite         |

---

## Architecture

Every rupee is traceable. The ERP is organised as multiple Django apps,
each with a strict internal structure (models / views / services /
selectors / forms), so business logic never leaks into views and queries
never leak into templates.

```
apps/
├── common/      BaseModel (UUID + audit + soft delete), managers, notification service,
│                current-user middleware, template tags, context processors
├── accounts/    Custom User (AbstractBaseUser), login throttling,
│                profile, admin
├── employees/   Employee HR profile, roles, role<->group sync, wallets,
│                daily work log, CBVs
├── finance/     Cash Book, Bank Ledger, derived balances, services
├── customers/   Customer profiles + credit limits + advance balance
├── services/    Service catalog + free-form categories + custom fields
│                (role-gated, per-service inputs captured on the bill;
│                formula pricing via total/income formulas + passthrough type)
├── billing/     Invoices + lines, credit settlement, 1-click WhatsApp share,
│                thermal receipts (80mm), customer-wallet payments, formula pricing
├── inventory/   Stock items, consumable tracking, Weighted Average Cost (WAC),
│                stock movements, cash book integration, low-stock alerts
├── reports/     P&L, bank/wallet statements, ledger, salary, analytics, CSV
├── pages/       Dashboard / home pages
└── workentry/   WorkEntry (history only; counter UI retired in Sprint 4.5)
```

### Sprint roadmap

| Sprint | Deliverables                    | Status |
|--------|---------------------------------|--------|
| 1      | Foundation, Auth, Roles, Employees, Layout | ✅ Done |
| 2      | Wallet Engine, Cash Book, Bank Ledger | ✅ Done |
| 3      | Customers, Services, Daily Work Log | ✅ Done |
| 4      | Billing, Dashboard, Reports, Analytics | ✅ Done |
| 4.5    | Formula-driven pricing, Customer Wallet, P&L income fix | ✅ Done |
| 5      | Inventory (Stock In/Out, WAC, Low-Stock Alerts, Cash Book Integration) | ✅ Done |
| 6      | 1-Click WhatsApp Share, Thermal Receipts (80mm), Low-Stock WhatsApp Alerts | ✅ Done |
| 7      | Bank Routing (AEPS Default), Staff Billing Permissions (Give/Revoke), Responsive UI | ✅ Done |

---

## Getting started (development)

```bash
# 1. Environment
cp .env.example .env

# 2. Dependencies
pip install --break-system-packages -r requirements.txt

# 3. Migrate + seed roles
python3 manage.py migrate
python3 manage.py seed_roles

# 4. Superuser (Owner account)
python3 manage.py createsuperuser

# 5. Run
python3 manage.py runserver
```

Open http://127.0.0.1:8000 — the root URL redirects to login.

> `manage.py` defaults to `config.settings.development` (SQLite, DEBUG on).
> For production set `DJANGO_SETTINGS_MODULE=config.settings.production`
> and provide database + secret values in `.env` (PostgreSQL).

### Tests & lint

```bash
python3 manage.py test
ruff check apps config manage.py
```

---

## Design decisions worth knowing

1. **One login account, one employee profile.**
   `accounts.User` (custom, built on `AbstractBaseUser` + `PermissionsMixin`)
   holds credentials; `employees.Employee` (OneToOne) holds HR data and the
   business `role`. BaseModel is inherited everywhere, so every table has
   UUID pk, audit FKs (`created_by` / `updated_by` / `deleted_by`) and
   soft delete (`deleted_at`, `is_active`).

2. **Soft delete is the only delete.**
   The default manager `objects` hides soft-deleted rows; `all_objects`
   exposes them. `BaseAdmin` disables hard deletes in the Django admin.

3. **Audit fields auto-fill.**
   `CurrentUserMiddleware` stores the request user in thread-local storage;
   `BaseModel.save()` stamps `created_by`/`updated_by` automatically.

4. **Roles are Django Groups.**
   `Employee.role` maps to a Group via `role_service.ROLE_GROUP_MAP`.
   `manage.py seed_roles` (idempotent) materialises groups and permissions.
   Views use `PermissionRequiredMixin` — Owner/Manager have full employee
   permissions; Accountant/Cashier/Counter/Staff are read-only.

5. **Business rules live in services.**
   `EmployeeService` is the only place employees are created/updated/
   deactivated. It generates the sequential `ANC-XXXX` code, creates the
   login atomically, keeps role groups in sync, and locks a deactivated
   employee out of login.

6. **Login throttling.**
   `accounts.services.authentication_service` counts failed attempts per
   username in cache and locks the account for 5 minutes after 5 failures.
   Swap the cache for Redis when scaling to multiple workers.

7. **Money is always `Decimal`.** `MONEY_MAX_DIGITS=18`, `MONEY_DECIMAL_PLACES=2`
   are the single source of truth; the `inr` template filter renders ₹ amounts.
   Balances are computed from transactions (never stored balances) from Sprint 2 on.

8. **Formula pricing without `eval()`.**
   `apps/common/services/formula.py` is a whitelisted recursive-descent parser
   (`+ - * /`, parentheses, unary minus, Decimal). A service's
   `total_formula` / `income_formula` evaluate against the bill line's
   custom-field variable names (+ `qty`, `price`); there is no way to reach
   Python imports, models, the filesystem or the network. `income_amount`
   (what the shop keeps) is stored per line and is the P&L income source,
   while `pass_through_amount` (money handed to the customer / transferred
   out) is booked to the staff wallet + ledgers separately.

---

## Security posture (already applied)

- Passwords hashed with Django's PBKDF2 defaults, never stored in plaintext.
- CSRF protection on all forms; logout is POST-only.
- Login brute-force lockout; `SESSION_COOKIE_HTTPONLY`, `CSRF_COOKIE_HTTPONLY`.
- Production hardening: HTTPS redirect, HSTS, secure cookies, `X_FRAME_OPTIONS=DENY`.
- Secrets only in `.env` (git-ignored); `.env.example` documents all variables.
- DB access via Django ORM / parameterised queries (no raw SQL injection surface).
- Uploaded files (employee photos) are validated by Django `ImageField`.

---

## Project structure

```
config/
├── settings/            base | development | production + .env loader
├── urls.py              root URL configuration
├── wsgi.py / asgi.py    deployment entry points
apps/
├── common/
│   ├── models.py        BaseModel (abstract)
│   ├── managers.py      ActiveManager / AllObjectsManager
│   ├── middleware.py    CurrentUserMiddleware
│   ├── templatetags/    inr, add_class, active_choices tags
│   └── context_processors.py
├── accounts/
│   ├── models/user.py   custom User
│   ├── services/        authentication_service (throttling)
│   ├── selectors/       user_selector
│   ├── forms.py / views.py / urls.py / admin.py
│   └── tests/
├── employees/
│   ├── models/employee.py   Employee + Role/Status/Gender choices
│   ├── services/            employee_service, role_service
│   ├── selectors/           employee_selector
│   ├── forms/ / views/ / urls.py / admin.py
│   ├── management/commands/seed_roles.py
│   └── tests/
└── pages/                dashboard
templates/                base + sidebar/topbar shell, module pages
static/css/site.css       ERP shell styling
```
