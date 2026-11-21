import uuid

from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    """One accepted upload: the file, who loaded it, what it held and its dataset notes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_name = models.CharField("файл", max_length=255)
    sha256 = models.CharField("контрольная сумма", max_length=64)
    file_format = models.CharField("формат", max_length=8)
    indicator = models.CharField("индикатор", max_length=8)
    sheet = models.CharField("лист", max_length=100, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField("загружен", auto_now_add=True)
    rows_total = models.PositiveIntegerField("строк", default=0)
    rows_created = models.PositiveIntegerField("новых записей", default=0)
    rows_updated = models.PositiveIntegerField("обновлено записей", default=0)
    real_cells = models.PositiveIntegerField("реальных ячеек", default=0)
    synthetic_cells = models.PositiveIntegerField("синтетических ячеек", default=0)
    sources_note = models.TextField("источники данных", blank=True)
    notes = models.TextField("примечания набора", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "загрузка"
        verbose_name_plural = "загрузки"

    @property
    def indicator_display(self):
        return "И" + self.indicator[1:] if self.indicator.startswith("I") else self.indicator

    def __str__(self):
        return f"{self.file_name} ({self.created_at:%d.%m.%Y %H:%M})"
