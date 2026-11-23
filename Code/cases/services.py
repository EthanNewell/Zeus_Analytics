from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import Review


@transaction.atomic
def add_review(*, actor, case, outcome, comment):
    if not actor.is_active or not actor.has_perms(["cases.view_case", "cases.add_review"]):
        raise PermissionDenied
    review = Review(case=case, author=actor, outcome=outcome, comment=comment)
    review.full_clean()
    review.save(force_insert=True)
    return review


EVIDENCE_MAX_BYTES = 5 * 1024 * 1024
