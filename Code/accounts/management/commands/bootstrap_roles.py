from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create the Specialist group and set its exact MVP permissions. Run after migrate."

    @transaction.atomic
    def handle(self, *args, **options):
        wanted = {
            ("cases", "view_case"),
            ("cases", "view_evidence"),
            ("cases", "view_review"),
            ("cases", "add_review"),
            ("cases", "import_cases"),
            ("cases", "export_cases"),
            ("cases", "run_analysis"),
        }
        available = {
            (p.content_type.app_label, p.codename): p
            for p in Permission.objects.select_related("content_type").filter(
                content_type__app_label="cases"
            )
        }
        if wanted - available.keys():
            raise CommandError("Missing permissions. Run manage.py migrate first.")
        group, _ = Group.objects.get_or_create(name="Specialist")
        group.permissions.set([available[key] for key in wanted])
        self.stdout.write(
            self.style.SUCCESS("Specialist permissions synchronized; users unchanged.")
        )
