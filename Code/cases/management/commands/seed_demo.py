from django.core.management.base import BaseCommand
from django.db import transaction

from cases.models import Case, Origin


class Command(BaseCommand):
    help = "Create three clearly synthetic UI examples without users, passwords or rule results."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for index, title in enumerate(
            [
                "Учебный участок: изменение ВРИ",
                "Учебный участок: история событий",
                "Учебный участок: неполные сведения",
            ],
            start=1,
        ):
            _, created = Case.objects.get_or_create(
                reference=f"DEMO-{index:03d}",
                defaults={
                    "title": title,
                    "origin": Origin.SYNTHETIC,
                    "is_demonstration": True,
                    "source_reference": "Синтетический пример каркаса. Первичные документы не приложены.",
                },
            )
            created_count += created
        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} demo cases. Existing cases unchanged.")
        )
