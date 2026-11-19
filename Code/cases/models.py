import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


class Origin(models.TextChoices):
    AUTHOR_MARKED_REAL = "author_marked_real", "Реальное по маркировке автора"
    SYNTHETIC = "synthetic", "Синтетическое"
    CALCULATED = "calculated", "Расчётное"
    UNKNOWN = "unknown", "Происхождение требует уточнения"


class Attention(models.TextChoices):
    """Case-level outcome of the latest analysis run. Owned by analysis.services."""

    NOT_RUN = "not_run", "Анализ не запускался"
    HIGH = "high", "Высокий приоритет проверки"
    NORMAL = "normal", "Требует проверки"
    LOW = "low", "Контекстный признак"
    INSUFFICIENT = "insufficient", "Недостаточно данных"
    NONE = "none", "Сигналов нет"


ATTENTION_ORDER = {
    Attention.HIGH: 0,
    Attention.NORMAL: 1,
    Attention.LOW: 2,
    Attention.INSUFFICIENT: 3,
    Attention.NONE: 4,
    Attention.NOT_RUN: 5,
}


class Case(models.Model):
    """One object under review: a land plot, a property item or a changed territory."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField("идентификатор", max_length=100, unique=True)
    title = models.CharField("название", max_length=300)
    cadastral_number = models.CharField("кадастровый номер", max_length=40, blank=True)
    object_kind = models.CharField("вид объекта", max_length=120, blank=True)
    address = models.CharField("адрес (местоположение)", max_length=500, blank=True)
    region = models.CharField("регион", max_length=120, blank=True)
    area_sq_m = models.FloatField("площадь, кв. м", null=True, blank=True)
    # [[lat, lon], ...] in WGS-84; plot contour when known.
    geometry = models.JSONField("контур (WGS-84)", null=True, blank=True)
    origin = models.CharField(
        "происхождение", max_length=32, choices=Origin, default=Origin.UNKNOWN
    )
    is_demonstration = models.BooleanField("демонстрационные данные", default=True)
    source_reference = models.CharField("основание / источник", max_length=500, blank=True)
    attention = models.CharField(
        "итог анализа", max_length=16, choices=Attention, default=Attention.NOT_RUN
    )
    attention_rank = models.PositiveSmallIntegerField(default=ATTENTION_ORDER[Attention.NOT_RUN])
    triggered_codes = models.CharField("сработавшие индикаторы", max_length=100, blank=True)
    signal_count = models.PositiveSmallIntegerField("число сработавших индикаторов", default=0)
    created_at = models.DateTimeField("создан", auto_now_add=True)
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        ordering = ["attention_rank", "-signal_count", "reference", "id"]
        verbose_name = "случай"
        verbose_name_plural = "случаи"
        permissions = [
            ("import_cases", "Can import cases"),
            ("export_cases", "Can export cases"),
            ("run_analysis", "Can run analysis"),
        ]
        indexes = [models.Index(fields=["attention_rank", "signal_count"])]

    def __str__(self):
        return f"{self.reference}: {self.title}"

    @property
    def triggered_list(self):
        return [code for code in self.triggered_codes.split(",") if code]


class Record(models.Model):
    """One imported row of one indicator table, with per-field provenance.

    ``facts`` maps a column key to {"value", "state", "origin", "cell", "label"}.
    ``state`` is "present", "missing" («нет данных», empty) or "absent" («—»: the event
    did not happen / not applicable). Values are JSON: ISO dates, numbers, text.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    indicator = models.CharField("индикатор", max_length=8, db_index=True)
    source_key = models.CharField("ключ записи", max_length=200)
    title = models.CharField("объект записи", max_length=300)
    cases = models.ManyToManyField(Case, related_name="records", verbose_name="случаи")
    batch = models.ForeignKey(
        "imports.ImportBatch", on_delete=models.PROTECT, related_name="records"
    )
    sheet = models.CharField("лист", max_length=100, blank=True)
    row_number = models.PositiveIntegerField("строка")
    facts = models.JSONField("факты", default=dict)
    author_mark = models.CharField("разметка автора", max_length=60, blank=True)
    is_demonstration = models.BooleanField("демонстрационные данные", default=True)
    updated_at = models.DateTimeField("обновлена", auto_now=True)

    class Meta:
        ordering = ["indicator", "row_number"]
        verbose_name = "запись индикатора"
        verbose_name_plural = "записи индикаторов"
        constraints = [
            models.UniqueConstraint(fields=["indicator", "source_key"], name="record_unique_key")
        ]

    def __str__(self):
        return f"{self.indicator}: {self.title}"


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
    url = models.URLField("ссылка", max_length=500, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    added_at = models.DateTimeField("добавлен", auto_now_add=True, null=True)

    class Meta:
        ordering = ["-added_at", "title", "id"]
        verbose_name = "документ"
        verbose_name_plural = "документы"


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
