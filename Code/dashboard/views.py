import csv
import re
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from analysis.contracts import RuleStatus
from analysis.models import AnalysisRun, RuleOutcome
from analysis.rules import RULES
from analysis.services import latest_outcomes
from cases.facts import parse_wkt_polygon
from cases.geometry import centroid
from cases.indicators import INDICATORS
from cases.models import Attention, Case, Evidence, Record
from cases.selectors import REVIEW_FILTERS, case_list, case_story, latest_reviews, svg_outline
from cases.services import add_review
from imports.models import ImportBatch

from .forms import ReviewForm

STATUS_LABELS = {
    RuleStatus.TRIGGERED: "Сработал",
    RuleStatus.NOT_TRIGGERED: "Не сработал",
    RuleStatus.INSUFFICIENT_DATA: "Недостаточно данных",
    RuleStatus.NOT_APPLICABLE: "Не применим",
}


def _filters(request):
    return {
        "query": request.GET.get("q", "").strip()[:200],
        "attention": request.GET.get("attention", ""),
        "indicator": request.GET.get("indicator", ""),
        "region": request.GET.get("region", ""),
        "review": request.GET.get("review", ""),
    }


def _current_outcomes():
    run = AnalysisRun.objects.first()
    if run is None:
        return None, []
    return run, list(run.outcomes.select_related("record"))


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def overview(request):
    run, outcomes = _current_outcomes()
    counts = Counter(Case.objects.values_list("attention", flat=True))
    per_indicator = []
    for code, indicator in INDICATORS.items():
        items = [outcome for outcome in outcomes if outcome.rule_code == code]
        compared = [outcome for outcome in items if outcome.expected_status]
        statuses = Counter(outcome.status for outcome in items)
        per_indicator.append(
            {
                "indicator": indicator,
                "total": len(items),
                "triggered": statuses[RuleStatus.TRIGGERED],
                "not_triggered": statuses[RuleStatus.NOT_TRIGGERED],
                "insufficient": statuses[RuleStatus.INSUFFICIENT_DATA],
                "compared": len(compared),
                "agreed": sum(outcome.agrees for outcome in compared),
            }
        )
    top = Case.objects.filter(attention__in=[Attention.HIGH, Attention.NORMAL])[:8]
    return render(
        request,
        "dashboard/overview.html",
        {
            "run": run,
            "total_cases": sum(counts.values()),
            "counts": {key: counts.get(key, 0) for key in Attention.values},
            "per_indicator": per_indicator,
            "top": top,
            "reviews": latest_reviews([case.pk for case in top]),
            "batch": ImportBatch.objects.first(),
            "max_total": max((row["total"] for row in per_indicator), default=0) or 1,
        },
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def cases(request):
    filters = _filters(request)
    objects = case_list(**filters)
    page = Paginator(objects, 25).get_page(request.GET.get("page"))
    reviews = latest_reviews([case.pk for case in page])
    query_string = request.GET.copy()
    query_string.pop("page", None)
    return render(
        request,
        "dashboard/case_list.html",
        {
            "page_obj": page,
            "filters": filters,
            "query_string": query_string.urlencode(),
            "reviews": reviews,
            "attention_choices": [
                (Attention.HIGH, "Высокий"),
                (Attention.NORMAL, "Требуют проверки"),
                (Attention.LOW, "Контекст"),
                (Attention.INSUFFICIENT, "Нет данных"),
                (Attention.NONE, "Без сигналов"),
            ],
            "indicators": INDICATORS.values(),
            "regions": Case.objects.exclude(region="")
            .order_by("region")
            .values_list("region", flat=True)
            .distinct(),
            "review_choices": REVIEW_FILTERS.items(),
            "run": AnalysisRun.objects.first(),
        },
    )


def detail_context(request, case, form=None):
    records = case.records.all()
    story = case_story(case, latest_outcomes(records))
    return {
        "case": case,
        "story": story,
        "outline": svg_outline(case.geometry),
        "grid": range(0, 241, 30),
        "review_form": form if form is not None else ReviewForm(),
        "reviews": case.reviews.select_related("author")
        if request.user.has_perm("cases.view_review")
        else [],
        "evidence": case.evidence.all() if request.user.has_perm("cases.view_evidence") else [],
        "status_labels": STATUS_LABELS,
    }


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def case_detail(request, case_id):
    case = get_object_or_404(Case, pk=case_id)
    return render(request, "dashboard/case_detail.html", detail_context(request, case))


@permission_required(["cases.view_case", "cases.add_review"], raise_exception=True)
@require_POST
def review_create(request, case_id):
    case = get_object_or_404(Case, pk=case_id)
    form = ReviewForm(request.POST)
    if form.is_valid():
        add_review(actor=request.user, case=case, **form.cleaned_data)
        messages.success(request, "Результат проверки сохранён в истории.")
        return redirect("dashboard:case_detail", case_id=case.id)
    return render(
        request, "dashboard/case_detail.html", detail_context(request, case, form), status=400
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def case_map(request):
    features = []
    for case in Case.objects.filter(geometry__isnull=False):
        features.append(
            {
                "kind": "plot",
                "id": str(case.pk),
                "title": case.title,
                "reference": case.reference,
                "attention": case.attention,
                "attention_label": case.get_attention_display(),
                "codes": [INDICATORS[code].code_display for code in case.triggered_list],
                "points": case.geometry,
            }
        )
    for record in Record.objects.filter(indicator="I2").prefetch_related("cases"):
        fact = record.facts.get("geometry", {})
        if fact.get("state") != "present":
            continue
        points = parse_wkt_polygon(fact["value"])
        linked = record.cases.first()
        features.append(
            {
                "kind": "zone",
                "id": str(linked.pk) if linked else "",
                "title": record.facts.get("location", {}).get("value") or record.title,
                "reference": record.facts.get("municipality", {}).get("value") or "",
                "attention": linked.attention if linked else "none",
                "attention_label": "Изменённая зона ПЗЗ / генплана",
                "codes": ["И2"],
                "points": points,
            }
        )
    without = Case.objects.filter(geometry__isnull=True).count()
    center = (
        centroid([feature["points"][0] for feature in features]) if features else [47.23, 39.72]
    )
    return render(
        request,
        "dashboard/map.html",
        {"features": features, "without_geometry": without, "center": center},
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def officials(request):
    records = list(Record.objects.filter(indicator="I10").prefetch_related("cases"))
    outcomes = latest_outcomes(records)
    people = sorted(
        (
            {
                "record": record,
                "outcome": outcomes.get(record.pk),
                "repeats": record.facts.get("repeats", {}).get("value") or 0,
                "episodes": [
                    re.sub(r"^\d+\)\s*", "", line.strip()).rstrip(";")
                    for line in (record.facts.get("comment", {}).get("value") or "").split("\n")
                    if line.strip()
                ],
                "cases": list(record.cases.all()),
            }
            for record in records
        ),
        key=lambda person: -person["repeats"],
    )
    return render(request, "dashboard/officials.html", {"people": people})


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def methodology(request):
    run, outcomes = _current_outcomes()
    rows = []
    for code, indicator in INDICATORS.items():
        items = [outcome for outcome in outcomes if outcome.rule_code == code]
        compared = [outcome for outcome in items if outcome.expected_status]
        rows.append(
            {
                "indicator": indicator,
                "rule": RULES.get(code),
                "compared": len(compared),
                "agreed": sum(outcome.agrees for outcome in compared),
                "mismatches": [outcome for outcome in compared if not outcome.agrees],
                "sources": sorted(
                    {
                        note
                        for note in ImportBatch.objects.filter(indicator=code).values_list(
                            "sources_note", flat=True
                        )
                        if note
                    }
                ),
            }
        )
    return render(
        request,
        "dashboard/methodology.html",
        {"run": run, "rows": rows, "status_labels": STATUS_LABELS},
    )


def csv_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


@permission_required(["cases.view_case", "cases.export_cases"], raise_exception=True)
@require_GET
def case_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="kod-prozrachnosti.csv"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Идентификатор",
            "Объект",
            "Кадастровый номер",
            "Регион",
            "Итог анализа",
            "Сработавшие индикаторы",
            "Объяснение",
            "Результат проверки сотрудника",
            "Дата проверки",
            "Проверил",
            "Демонстрационные данные",
        ]
    )
    objects = list(case_list(**_filters(request)))
    reviews = latest_reviews([case.pk for case in objects])
    outcomes = {}
    for outcome in RuleOutcome.objects.filter(
        run=AnalysisRun.objects.first(), status=RuleStatus.TRIGGERED
    ).prefetch_related("record__cases"):
        for case in outcome.record.cases.all():
            outcomes.setdefault(case.pk, []).append(
                f"{INDICATORS[outcome.rule_code].code_display}: {outcome.explanation}"
            )
    for case in objects:
        review = reviews.get(case.pk)
        writer.writerow(
            [
                csv_cell(value)
                for value in (
                    case.reference,
                    case.title,
                    case.cadastral_number,
                    case.region,
                    case.get_attention_display(),
                    ", ".join(INDICATORS[code].code_display for code in case.triggered_list),
                    " | ".join(outcomes.get(case.pk, [])),
                    review.get_outcome_display() if review else "",
                    timezone.localtime(review.created_at).strftime("%d.%m.%Y %H:%M")
                    if review
                    else "",
                    review.author.username if review else "",
                    "да" if case.is_demonstration else "нет",
                )
            ]
        )
    return response


@permission_required(["cases.view_case", "cases.view_evidence"], raise_exception=True)
@require_GET
def evidence_download(request, evidence_id):
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    if not evidence.file:
        raise Http404
    try:
        file = evidence.file.open("rb")
    except FileNotFoundError as error:
        raise Http404 from error
    return FileResponse(
        file,
        as_attachment=True,
        filename=evidence.download_name,
        content_type="application/octet-stream",
    )
