from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.roles import ROLES


class Command(BaseCommand):
    help = "Create the role groups and set their exact permissions. Run after migrate."

    @transaction.atomic
    def handle(self, *args, **options):
        available = {
            p.codename: p
            for p in Permission.objects.select_related("content_type").filter(
                content_type__app_label="cases"
            )
        }
        for role in ROLES:
            missing = set(role.permissions) - available.keys()
            if missing:
                raise CommandError("Missing permissions. Run manage.py migrate first.")
            group, _ = Group.objects.get_or_create(name=role.group)
            group.permissions.set([available[codename] for codename in role.permissions])
        self.stdout.write(self.style.SUCCESS("Role permissions synchronized; users unchanged."))
