import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.roles import ROLES

DEMO = {"Specialist": "specialist", "Controller": "controller", "Head": "head"}
# the open demonstration account the sign-in page names: «почта» 12345, password 12345,
# full rights of the head of department; its name is the one drawn in the Figma frames
GUEST = {"username": "12345", "password": "12345", "group": "Head", "name": ("Алексей", "М.")}


class Command(BaseCommand):
    help = (
        "Create one demo account per role. Existing accounts keep their password; a new one "
        "gets the password from --password-<role> or a random one (printed once). The open "
        "demonstration account 12345 / 12345 is always (re)set."
    )

    def add_arguments(self, parser):
        for username in DEMO.values():
            parser.add_argument(f"--password-{username}", dest=f"password_{username}", default="")
        parser.add_argument(
            "--reset", action="store_true", help="Set new passwords for existing accounts too"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("bootstrap_roles", verbosity=0)
        User = get_user_model()
        for role in ROLES:
            username = DEMO[role.group]
            user, created = User.objects.get_or_create(username=username)
            given = options[f"password_{username}"]
            if created or options["reset"] or given:
                password = given or secrets.token_urlsafe(9)
                user.set_password(password)
                user.save()
                shown = password
            else:
                shown = "(пароль не менялся)"
            user.groups.set([Group.objects.get(name=role.group)])
            self.stdout.write(f"{role.label}: {username} / {shown}")
        if getattr(settings, "ENABLE_SYNTHETIC_LOGIN", False):
            guest, created = User.objects.get_or_create(username=GUEST["username"])
            guest.first_name, guest.last_name = GUEST["name"]
            if created:
                guest.set_password(GUEST["password"])
            guest.save()
            guest.groups.set([Group.objects.get(name=GUEST["group"])])
            self.stdout.write(f"Демонстрационная запись: {GUEST['username']} / {GUEST['password']}")
