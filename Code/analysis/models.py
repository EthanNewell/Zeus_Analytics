import uuid

from django.conf import settings
from django.db import models

from .contracts import Priority, RuleStatus


class AnalysisRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    started_at = models.DateTimeField("запуск", auto_now_add=True)
    duration_ms = models.PositiveIntegerField("длительность, мс", default=0)
    rules = models.JSONField("версии правил", default=dict)
    records_count = models.PositiveIntegerField("записей", default=0)
    cases_count = models.PositiveIntegerField("случаев", default=0)
    triggered_count = models.PositiveIntegerField("сработало", default=0)
    compared_count = models.PositiveIntegerField("сверено с разметкой", default=0)
    agreed_count = models.PositiveIntegerField("совпало с разметкой", default=0)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "запуск анализа"
        verbose_name_plural = "запуски анализа"


class RuleOutcome(models.Model):
    """Stored, immutable result of one rule on one record in one run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="outcomes")
    record = models.ForeignKey("cases.Record", on_delete=models.CASCADE, related_name="outcomes")
    rule_code = models.CharField("индикатор", max_length=8)
    rule_version = models.CharField("версия", max_length=16)
    status = models.CharField(
        "статус", max_length=20, choices=[(s.value, s.value) for s in RuleStatus]
    )
    priority = models.CharField(
        "приоритет", max_length=8, choices=[(p.value, p.value) for p in Priority]
    )
    explanation = models.TextField("объяснение")
    metrics = models.JSONField("расчёт", default=list)
    used_fields = models.JSONField("использованные факты", default=list)
    missing_fields = models.JSONField("недостающие данные", default=list)
    expected_status = models.CharField("разметка исследования", max_length=20, blank=True)
    is_demonstration = models.BooleanField("на демонстрационных данных", default=True)

    class Meta:
        ordering = ["rule_code", "id"]
        indexes = [models.Index(fields=["run", "rule_code"])]

    @property
    def agrees(self):
        return not self.expected_status or self.expected_status == self.status
