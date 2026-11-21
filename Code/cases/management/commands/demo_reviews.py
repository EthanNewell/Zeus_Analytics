"""Three demonstration decisions for the public demo: one per outcome.

They show how a decision moves a case from its risk tab to «Подтверждено» / «Не подтверждено»
and how comments appear on the object graph. Every comment starts with «Демонстрационная
запись». «Подтверждено» goes only to an object without a cadastral number (a synthetic one):
a real plot is never marked as confirmed.

    python manage.py demo_reviews
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cases.models import Case, Review, ReviewOutcome
from cases.services import add_review

PLAN = (
    (
        "ОБ-042B30F4",
        "controller",
        ReviewOutcome.CONFIRMED,
        "Демонстрационная запись. Торги с одним участником, договор по начальной цене; "
        "основания для проверки подтверждены, материалы переданы руководителю.",
    ),
    (
        "61:02:0600012:1388",
        "specialist",
        ReviewOutcome.NOT_CONFIRMED,
        "Демонстрационная запись. Повтор должностного лица объясняется распределением дел "
        "по должности; связи с приобретателем не найдено.",
    ),
    (
        "61:02:0600010:2843",
        "specialist",
        ReviewOutcome.NEEDS_INFORMATION,
        "Демонстрационная запись. Нужна выписка о переходе прав и дата первого проекта "
        "изменения категории.",
    ),
)


class Command(BaseCommand):
    help = "Add one demonstration decision per outcome (idempotent)."

    def handle(self, *args, **options):
        users = get_user_model().objects
        for reference, username, outcome, comment in PLAN:
            case = Case.objects.filter(reference=reference).first()
            if case is None:
                raise CommandError(f"нет объекта {reference}: сначала load_tables demo_data")
            if Review.objects.filter(case=case, comment=comment).exists():
                continue
            add_review(
                actor=users.get(username=username), case=case, outcome=outcome, comment=comment
            )
            self.stdout.write(f"{reference}: {outcome.label}")
