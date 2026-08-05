"""Read-only data access for User records. Views never query User directly."""
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSelector:
    @staticmethod
    def get_by_username(username: str):
        return User.objects.filter(username__iexact=username).first()

    @staticmethod
    def get_by_id(user_id):
        return User.objects.filter(id=user_id).first()

    @staticmethod
    def active_users():
        return User.objects.filter(is_active=True).order_by("username")
