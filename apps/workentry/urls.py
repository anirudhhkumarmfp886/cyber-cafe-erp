"""
WorkEntry URL routes were retired in Sprint 4.5.

The work-entry counter UI no longer has public routes; saved work entries
were migrated to invoices (see ``billing.0006``). The app stays installed so
its model and migration history remain queryable through Django admin.
"""
