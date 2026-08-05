"""View layer for the accounts app."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views import View

from apps.accounts.forms import OwnerSignupForm, ThrottledAuthenticationForm
from apps.accounts.services import authentication_service
from apps.accounts.services.owner_bootstrap_service import OwnerBootstrapService


class ThrottledLoginView(LoginView):
    """Login view wired to the brute-force lockout service."""

    template_name = "registration/login.html"
    authentication_form = ThrottledAuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Expose whether the first-run signup link should be shown.
        context["show_signup"] = OwnerBootstrapService.is_bootstrap_required()
        return context

    def form_valid(self, form):
        authentication_service.clear_failed_attempts(form.cleaned_data.get("username"))
        return super().form_valid(form)

    def form_invalid(self, form):
        username = self.request.POST.get("username", "")
        if username:
            attempts = authentication_service.record_failed_attempt(username)
            remaining = settings.LOGIN_ATTEMPT_THRESHOLD - attempts
            if remaining > 0:
                form.add_error(
                    None,
                    f"Invalid username or password. {remaining} attempt(s) remaining before lockout.",
                )
        return super().form_invalid(form)


class OwnerSignupView(View):
    """Create the very first Owner account. Disabled once an owner exists."""

    template_name = "registration/signup.html"

    def _guard(self, request):
        if not OwnerBootstrapService.is_bootstrap_required():
            messages.info(request, "An owner account already exists. Please sign in instead.")
            return redirect("accounts:login")
        return None

    def get(self, request):
        guard = self._guard(request)
        if guard:
            return guard
        return render(request, self.template_name, {"form": OwnerSignupForm()})

    def post(self, request):
        guard = self._guard(request)
        if guard:
            return guard
        form = OwnerSignupForm(request.POST)
        if form.is_valid():
            try:
                user = OwnerBootstrapService.create_owner(
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password"],
                    email=form.cleaned_data.get("email", ""),
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                login(request, user)
                messages.success(
                    request,
                    "Welcome, Owner! Your account is ready. Update your password after first login.",
                )
                return redirect("pages:dashboard")
        return render(request, self.template_name, {"form": form})


@login_required
def profile(request):
    """Shows the signed-in user's account and linked employee profile."""
    employee = getattr(request.user, "employee", None)
    return render(
        request,
        "accounts/profile.html",
        {"page_title": "My Profile", "employee": employee},
    )
