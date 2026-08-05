"""
EmployeeSelector — read-only access to Employee data.

Views and templates go through these helpers so that query optimisation
(select_related) and filtering rules live in one place.
"""
from django.contrib.auth import get_user_model

from apps.employees.models import Employee

User = get_user_model()


class EmployeeSelector:
    @staticmethod
    def list_active():
        return Employee.objects.select_related("user").order_by("-created_at")

    @staticmethod
    def get_by_id(employee_id):
        return Employee.objects.select_related("user").filter(id=employee_id).first()

    @staticmethod
    def get_by_user(user):
        return Employee.objects.select_related("user").filter(user=user).first()

    @staticmethod
    def by_role(role):
        return Employee.objects.filter(role=role)

    @staticmethod
    def count_active() -> int:
        return Employee.objects.count()

    @staticmethod
    def count_users() -> int:
        return User.objects.filter(is_active=True).count()
