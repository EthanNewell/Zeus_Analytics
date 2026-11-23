from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import Evidence, Origin, Review


@transaction.atomic
def add_review(*, actor, case, outcome, comment):
    if not actor.is_active or not actor.has_perms(["cases.view_case", "cases.add_review"]):
        raise PermissionDenied
    review = Review(case=case, author=actor, outcome=outcome, comment=comment)
    review.full_clean()
    review.save(force_insert=True)
    return review


# the formats named in the upload window: PDF, DOCX, XLSX, JPG, PNG, TIFF
EVIDENCE_TYPES = {".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
EVIDENCE_MAX_BYTES = 5 * 1024 * 1024


@transaction.atomic
def add_evidence(
    *,
    actor,
    case=None,
    title="",
    url="",
    file=None,
    source_reference="",
    origin=Origin.UNKNOWN,
    kind="",
    note="",
):
    """Keep a document file or a link, linked to a case or common; facts and signals stay as they are."""
    if not actor.is_active or not actor.has_perms(["cases.view_case", "cases.add_evidence"]):
        raise PermissionDenied
    if not url and not file:
        raise ValidationError("Приложите файл или укажите ссылку.")
    if url and not url.lower().startswith(("https://", "http://")):
        raise ValidationError("Ссылка должна начинаться с http:// или https://.")
    download_name = "document"
    if file:
        suffix = Path(file.name).suffix.lower()
        if suffix not in EVIDENCE_TYPES:
            raise ValidationError("Допустимы PDF, DOCX, XLSX, JPG, PNG и TIFF.")
        if file.size > EVIDENCE_MAX_BYTES:
            raise ValidationError("Файл больше 5 МБ.")
        download_name = Path(file.name).name[:200]
        title = title or download_name
    if origin not in (Origin.UNKNOWN, Origin.SYNTHETIC, Origin.AUTHOR_MARKED_REAL):
        origin = Origin.UNKNOWN
    evidence = Evidence(
        case=case,
        title=(title.strip() or url.strip() or "Документ")[:200],
        kind=kind,
        note=note.strip()[:2000],
        url=url.strip(),
        source_reference=source_reference.strip()[:500],
        origin=origin,
        added_by=actor,
        download_name=download_name,
    )
    if file:
        evidence.file = file
    evidence.full_clean()
    evidence.save(force_insert=True)
    return evidence
