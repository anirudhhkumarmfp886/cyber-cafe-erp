# AK NAZAR CYBER CAFE ERP

# परियोजना परिचय

यह Django आधारित ERP (Enterprise Resource Planning) प्रोजेक्ट है, जिसे AK Nazar Cyber Cafe के संचालन के लिए विकसित किया गया है।

यह प्रोजेक्ट वर्तमान में निम्न मॉड्यूल प्रदान करता है:

- उपयोगकर्ता प्रमाणीकरण (Authentication)
- कर्मचारी प्रबंधन (Employee Management)
- Wallet Management
- Cash Book
- Bank Ledger
- Dashboard
- Audit आधारित Base Model
- Soft Delete System
- Role आधारित Access Control

---

# प्रयुक्त तकनीक (Tech Stack)

| तकनीक | विवरण |
|--------|--------|
| Language | Python 3.11 |
| Framework | Django 5.2.13 |
| Database (Development) | SQLite |
| Database (Production) | PostgreSQL |
| Frontend | Bootstrap 5 |
| Static Files | WhiteNoise |
| Image Support | Pillow |
| Server | Gunicorn |
| Environment | python-dotenv |

---

# Project Structure

```
workspace/

│
├── manage.py
├── requirements.txt
├── db.sqlite3
├── config/
│
├── apps/
│   ├── accounts/
│   ├── common/
│   ├── employees/
│   ├── finance/
│   └── pages/
│
├── templates/
│
├── static/
│
└── .env.example
```

---

# उपलब्ध Django Apps

## 1. accounts

यह App निम्न कार्य संभालता है:

- Login
- Logout
- Owner Signup
- Profile
- Custom User Model
- Authentication Service
- User Selector
- Owner Bootstrap Service

मुख्य URL

```
/accounts/login/
/accounts/logout/
/accounts/signup/
/accounts/profile/
```

---

## 2. employees

यह App कर्मचारी प्रबंधन के लिए है।

उपलब्ध सुविधाएँ

- Employee List
- Employee Detail
- Employee Create
- Employee Update
- Employee Deactivate
- Wallet List
- Wallet Detail

Management Command

```
seed_roles
```

मुख्य URL

```
/employees/
/employees/add/
/employees/<uuid>/
/employees/<uuid>/edit/
/employees/<uuid>/deactivate/
/employees/wallets/
/employees/wallets/<uuid>/
```

---

## 3. finance

Finance Module में वर्तमान में निम्न सुविधाएँ उपलब्ध हैं।

### CashBook

- CashBook List
- CashBook Delete

### Bank

- Bank Account List
- Bank Account Detail

मुख्य URL

```
/finance/cashbook/
/finance/cashbook/<uuid>/delete/

/finance/bank/
/finance/bank/<uuid>/
```

---

## 4. common

यह पूरे ERP का Shared Infrastructure Module है।

इसमें उपलब्ध हैं

- Base Model
- Custom Managers
- Middleware
- Context Processor
- Template Tags
- Reference Service

---

## 5. pages

Dashboard उपलब्ध कराता है।

मुख्य URL

```
/
```

---

# Authentication

Project Custom User Model उपयोग करता है।

```
AUTH_USER_MODEL = accounts.User
```

Default Login URL

```
/accounts/login/
```

Login के बाद Redirect

```
Dashboard
```

Logout के बाद Redirect

```
Login Page
```

---

# Middleware

Project में Custom Middleware उपलब्ध है।

```
apps.common.middleware.CurrentUserMiddleware
```

इसका उपयोग Audit Fields को Maintain करने के लिए किया गया है।

---

# Installed Applications

```
apps.common
apps.accounts
apps.employees
apps.finance
apps.pages
```

---

# Database

Development

```
SQLite
```

Production

```
PostgreSQL
```

---

# Static Files

```
static/
```

---

# Media Files

```
media/
```

---

# Environment Setup

सबसे पहले

```
cp .env.example .env
```

---

# Dependencies Install करें

```
pip install -r requirements.txt
```

---

# Database Migration

```
python manage.py migrate
```

---

# Roles Seed करें

```
python manage.py seed_roles
```

---

# Superuser बनाएं

```
python manage.py createsuperuser
```

---

# Development Server चलाएं

```
python manage.py runserver
```

---

# Project URLs

| URL | उद्देश्य |
|------|----------|
| / | Dashboard |
| /admin/ | Django Admin |
| /accounts/ | Authentication |
| /employees/ | Employee Module |
| /finance/ | Finance Module |

---

# Testing

Project में विभिन्न Modules के लिए Tests उपलब्ध हैं।

उदाहरण

```
apps/accounts/tests/
apps/common/tests/
apps/employees/tests/
apps/finance/tests/
```

सभी Tests चलाने हेतु

```
python manage.py test
```

---

# Code Quality

Project में Ruff Linter उपयोग किया गया है।

Run करें

```
ruff check apps config manage.py
```

---

# वर्तमान Templates

Project में निम्न Templates उपलब्ध हैं।

```
registration/login.html
registration/signup.html

employees/
    employee_list.html
    employee_detail.html
    employee_form.html
    wallet_list.html
    wallet_detail.html

finance/
    bank_list.html
    bank_detail.html
    cashbook_list.html

accounts/
    profile.html

pages/
    dashboard.html
```

---

# वर्तमान Features (Source Code के अनुसार)

✔ Custom User Model

✔ Authentication

✔ Owner Signup

✔ Dashboard

✔ Employee Management

✔ Employee Wallet

✔ CashBook

✔ Bank Ledger

✔ Soft Delete Infrastructure

✔ Audit Fields Infrastructure

✔ Current User Middleware

✔ Django Admin

✔ Role Seed Command

✔ Unit Tests

---

# Production Settings

Project में अलग Configuration उपलब्ध है।

```
config/settings/

base.py
development.py
production.py
```

Production Environment में PostgreSQL Configuration उपयोग किया जाता है।

---

# आवश्यक Python Packages

```
Django
python-dotenv
Pillow
whitenoise
psycopg
gunicorn
ruff
```

---

# लेखक

Project Name

AK NAZAR CYBER CAFE ERP