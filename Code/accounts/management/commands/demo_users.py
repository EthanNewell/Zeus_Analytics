import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.roles import ROLES

DEMO = {"Specialist": "specialist", "Controller": "controller", "Head": "head"}


class Command(BaseCommand):
    help = "Create one demo account per role with a fresh random password (printed once)."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("bootstrap_roles", verbosity=0)
        User = get_user_model()
        for role in ROLES:
            username = DEMO[role.group]
            password = secrets.token_urlsafe(9)
            user, _ = User.objects.get_or_create(username=username)
            user.set_password(password)
            user.save()
            user.groups.set([Group.objects.get(name=role.group)])
            self.stdout.write(f"{role.label}: {username} / {password}")
