import time
import uuid

from django.core.exceptions import PermissionDenied
from django.db import transaction

from cases.indicators import INDICATORS
from cases.models import ATTENTION_ORDER, Attention, Case, Record

from .contracts import Priority, RuleStatus
from .models import AnalysisRun, RuleOutcome
from .rules import RULES, expected_status


class AnalysisNotConfigured(Exception):
    pass


@transaction.atomic
def run_analysis(*, actor, case_ids=None):
    """Evaluate every rule on every record (or on the records of the given cases)."""
    if not actor.is_active or not actor.has_perms(["cases.view_case", "cases.run_analysis"]):
        raise PermissionDenied
    started = time.monotonic()
    records = Record.objects.prefetch_related("cases")
    if case_ids:
        try:
            case_ids = [uuid.UUID(str(value)) for value in case_ids]
        except ValueError as error:
            raise AnalysisNotConfigured("Неверный идентификатор объекта.") from error
        # a record shared by several cases (И2, И10) touches its neighbours too: take every
        # record of every affected case, so each verdict is computed from all its records
        affected = Case.objects.filter(records__cases__id__in=case_ids).values("pk")
        records = records.filter(cases__in=affected).distinct()
    records = list(records)
    if not records:
        raise AnalysisNotConfigured(
            "Нет загруженных записей: сначала импортируйте таблицы индикаторов."
        )
    run = AnalysisRun.objects.create(
        started_by=actor, rules={code: rule.version for code, rule in RULES.items()}
    )
    outcomes, cases = [], {}
    for record in records:
        rule = RULES.get(record.indicator)
        if rule is None:
            continue
        result = rule.evaluate(record.facts)
        expected = expected_status(record.author_mark)
        used_demo = any(
            record.facts.get(key, {}).get("origin") in ("synthetic", "unknown")
            for key in result.used
        )
        outcomes.append(
            RuleOutcome(
                run=run,
                record=record,
                rule_code=rule.code,
                rule_version=rule.version,
                status=result.status.value,
                priority=result.priority.value,
                explanation=result.explanation,
                metrics=[list(item) for item in result.metrics],
                used_fields=result.used,
                missing_fields=result.missing,
                expected_status=expected,
                is_demonstration=used_demo or record.is_demonstration,
            )
        )
        for case in record.cases.all():
            cases.setdefault(case.pk, case)
    RuleOutcome.objects.bulk_create(outcomes)
    by_case = {pk: [] for pk in cases}
    record_cases = {record.pk: [case.pk for case in record.cases.all()] for record in records}
    for outcome in outcomes:
        for case_pk in record_cases[outcome.record_id]:
            by_case[case_pk].append(outcome)
    for case_pk, case in cases.items():
        attention, codes = summarize(by_case[case_pk])
        case.attention = attention
        case.attention_rank = ATTENTION_ORDER[attention]
        case.triggered_codes = ",".join(codes)
        case.signal_count = len(codes)
    Case.objects.bulk_update(
        cases.values(), ["attention", "attention_rank", "triggered_codes", "signal_count"]
    )
    if not case_ids:
        # objects left without records (a re-import unlinked them) keep no stale verdict
        Case.objects.exclude(pk__in=cases).update(
            attention=Attention.NONE,
            attention_rank=ATTENTION_ORDER[Attention.NONE],
            triggered_codes="",
            signal_count=0,
        )
    compared = [outcome for outcome in outcomes if outcome.expected_status]
    run.records_count = len(outcomes)
    run.cases_count = len(cases)
    run.triggered_count = sum(outcome.status == RuleStatus.TRIGGERED for outcome in outcomes)
    run.compared_count = len(compared)
    run.agreed_count = sum(outcome.agrees for outcome in compared)
    run.duration_ms = int((time.monotonic() - started) * 1000)
    run.save()
    return run


def summarize(outcomes):
    """Case attention from its rule outcomes. Context indicators never raise it to high."""
    triggered = [outcome for outcome in outcomes if outcome.status == RuleStatus.TRIGGERED]
    codes = sorted({outcome.rule_code for outcome in triggered}, key=lambda code: int(code[1:]))
    main = {code for code in codes if INDICATORS[code].kind == "main"}
    if any(outcome.priority == Priority.HIGH for outcome in triggered) or len(main) >= 2:
        return Attention.HIGH, codes
    if main:
        return Attention.NORMAL, codes
    if triggered:
        return Attention.LOW, codes
    if any(outcome.status == RuleStatus.INSUFFICIENT_DATA for outcome in outcomes):
        return Attention.INSUFFICIENT, codes
    return Attention.NONE, codes


def latest_outcomes(records):
    """The newest outcome for each record, keyed by record id."""
    latest = {}
    for outcome in (
        RuleOutcome.objects.filter(record__in=records)
        .select_related("run")
        .order_by("record_id", "-run__started_at")
    ):
        latest.setdefault(outcome.record_id, outcome)
    return latest
