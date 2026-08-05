from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("signup/", views.OwnerSignupView.as_view(), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
]
