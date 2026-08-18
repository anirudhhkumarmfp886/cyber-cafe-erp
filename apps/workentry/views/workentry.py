"""
WorkEntry views were retired in Sprint 4.5.

The counter UI was replaced by the billing surface (``billing.0006`` migrated
every saved work entry to an invoice). No ``workentry`` views are registered
any more; the app remains installed so the model and its data stay available
through Django admin and the reports layer.
"""
