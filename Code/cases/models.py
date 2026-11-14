import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


class Origin(models.TextChoices):
    AUTHOR_MARKED_REAL = "author_marked_real", "Реальное по маркировке автора"
    SYNTHETIC = "synthetic", "Синтетическое"
    CALCULATED = "calculated", "Расчётное"
    UNKNOWN = "unknown", "Происхождение требует уточнения"


class Case(models.Model):
    """Minimal integration model. Detailed land facts belong to the data workstream."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField("идентификатор", max_length=100, unique=True)
    title = models.CharField("название", max_length=200)
    cadastral_number = models.CharField("кадастровый номер", max_length=40, blank=True)
    origin = models.CharField(
        "происхождение", max_length=32, choices=Origin, default=Origin.UNKNOWN
    )
    is_demonstration = models.BooleanField("демонстрационные данные", default=True)
    source_reference = models.CharField("основание / источник", max_length=500, blank=True)
    created_at = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "случай"
        verbose_name_plural = "случаи"
        permissions = [
            ("import_cases", "Can import cases"),
            ("export_cases", "Can export cases"),
            ("run_analysis", "Can run analysis"),
        ]

    def __str__(self):
        return f"{self.reference}: {self.title}"


def evidence_upload_path(instance, filename):
    return f"evidence/{instance.case_id}/{uuid.uuid4().hex}{Path(filename).suffix[:12]}"


class Evidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name="evidence")
    title = models.CharField("название", max_length=200)
    file = models.FileField("файл", upload_to=evidence_upload_path, blank=True)
    download_name = models.CharField("имя для скачивания", max_length=200, default="document")
    origin = models.CharField(
        "происхождение", max_length=32, choices=Origin, default=Origin.UNKNOWN
    )
    source_reference = models.CharField("источник", max_length=500, blank=True)

    class Meta:
        ordering = ["title", "id"]
        verbose_name = "источник"
        verbose_name_plural = "источники"


class ReviewOutcome(models.TextChoices):
    CONFIRMED = "confirmed", "Основания для дальнейшей проверки подтверждены"
    NOT_CONFIRMED = "not_confirmed", "Предположение не подтвердилось"
    NEEDS_INFORMATION = "needs_information", "Нужны дополнительные сведения"


class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name="reviews")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    outcome = models.CharField("результат", max_length=32, choices=ReviewOutcome)
    comment = models.TextField("обоснование", max_length=4000)
    created_at = models.DateTimeField("дата проверки", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "запись проверки"
        verbose_name_plural = "история проверок"
