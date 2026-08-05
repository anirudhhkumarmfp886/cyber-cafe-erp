"""
accounts.User — the single authentication identity for the whole ERP.

Design notes:
  * Built on AbstractBaseUser + PermissionsMixin instead of AbstractUser so
    it can inherit the project-wide BaseModel (audit + soft-delete) without
    field clashes, and so the identifier can evolve (username today, phone
    login later) without migrations that rebuild the table.
  * ``objects`` is the BaseUserManager; soft-deleted users are hidden by the
    ActiveManager from BaseModel, which also locks them out of auth.
  * Every login account maps to exactly one Employee profile (Sprint 1),
    which carries the business role (Owner / Manager / Staff ...).
"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.accounts.managers import UserManager
from apps.common.models import BaseModel


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True, db_index=True)
    email = models.EmailField(unique=True, null=True, blank=True, db_index=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.get_full_name() or self.username

    def get_full_name(self):
        full_name = " ".join(part for part in (self.first_name, self.last_name) if part).strip()
        return full_name or self.username

    def get_short_name(self):
        return self.first_name or self.username
