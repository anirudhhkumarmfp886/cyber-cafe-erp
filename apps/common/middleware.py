"""
CurrentUserMiddleware.

Stores the authenticated request user in thread-local storage so that
``BaseModel.save()`` can automatically populate the audit fields
(created_by / updated_by / deleted_by) without every view, form, admin,
or service having to pass the user explicitly.

Safety considerations:
  * The value is cleared after every request, so it cannot leak from one
    request into the next, even in long-running workers.
  * Outside a request (management commands, tests, shell) it simply
    returns None and audit FKs stay empty.
"""
import threading

_local = threading.local()


def get_current_user():
    """Return the user bound to the current thread, or None."""
    return getattr(_local, "user", None)


def _set_current_user(user) -> None:
    _local.user = user


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        _set_current_user(user)
        try:
            response = self.get_response(request)
        finally:
            # Always clear so nothing leaks across requests.
            _set_current_user(None)
        return response
