"""Forms for the accounts app."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

from apps.accounts.services import authentication_service

User = get_user_model()


class ThrottledAuthenticationForm(AuthenticationForm):
    """Login form that rejects credentials for temporarily locked users."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Username", "autofocus": True}
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"})
    )

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and authentication_service.is_locked_out(username):
            raise forms.ValidationError(
                "Too many failed login attempts. Please try again in a few minutes."
            )
        return super().clean()


class UserCreateForm(forms.ModelForm):
    """Programmatic user creation form used by the Employee service flow."""

    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "email", "phone", "first_name", "last_name"]


class OwnerSignupForm(forms.Form):
    """First-run owner bootstrap form (only usable before an owner exists)."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Choose a username", "autofocus": True}
        ),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com (optional)"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Create a strong password"}),
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Repeat password"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned
