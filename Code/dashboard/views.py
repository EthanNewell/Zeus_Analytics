import csv
import re
from collections import Counter
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from analysis.contracts import RuleStatus
from analysis.models import AnalysisRun, RuleOutcome
from analysis.rules import RULES
from analysis.services import latest_outcomes
from cases.facts import parse_wkt_polygon
from cases.geometry import centroid
from cases.indicators import INDICATORS
from cases.models import Attention, Case, Evidence, Record, Risk
from cases.selectors import (
    REVIEW_FILTERS,
    case_graph,
    case_list,
    case_story,
    evidence_url,
    latest_reviews,
    queue_counts,
    recent_events,
    svg_outline,
)
from cases.services import add_review
from cases.sources import sources_with_usage
from imports.models import ImportBatch

from .forms import ReviewForm

STATUS_LABELS = {
    RuleStatus.TRIGGERED: "Сработал",
    RuleStatus.NOT_TRIGGERED: "Не сработал",
    RuleStatus.INSUFFICIENT_DATA: "Нет данных",
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


HISTORY_KINDS = {"review": "Решения", "import": "Загрузки", "analysis": "Анализы"}
RISK_COLOURS = {"high": "#f92e2e", "medium": "#ff941a", "low": "#039a00"}
CATEGORY_COLOURS = ["#b6d3f0", "#c2f0b6", "#d2b7f0", "#f0eab6", "#9ed9cf", "#f5c6b8", "#c9cfd8"]


def indicator_stats(outcomes):
    """Per indicator: totals, statuses and agreement with the research marks."""
    rows = []
    for code, indicator in INDICATORS.items():
        items = [outcome for outcome in outcomes if outcome.rule_code == code]
        compared = [outcome for outcome in items if outcome.expected_status]
        statuses = Counter(outcome.status for outcome in items)
        rows.append(
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
    return rows


def recommendations(queue, per_indicator, run):
    """Plain next steps derived from the data; no model, no guesses."""
    items = []
    if queue.get("high"):
        items.append(
            {
                "tone": "high",
                "text": f"{queue['high']} объект(ов) высокого риска ждут решения. Начните с них.",
                "url": reverse("dashboard:case_list") + "?attention=high",
            }
        )
    if queue.get("needs_information"):
        items.append(
            {
                "tone": "medium",
                "text": f"По {queue['needs_information']} объект(ам) запрошены сведения. Проверьте, пришли ли документы.",
                "url": reverse("dashboard:case_list") + "?review=needs_information",
            }
        )
    gaps = sorted(
        (row for row in per_indicator if row["insufficient"]), key=lambda row: -row["insufficient"]
    )
    for row in gaps[:2]:
        items.append(
            {
                "tone": "info",
                "text": f"{row['indicator'].code_display}: у {row['insufficient']} записей нет данных для вывода. Нужны выписки и документы из источников индикатора.",
                "url": reverse("dashboard:case_list")
                + f"?indicator={row['indicator'].code}&attention=insufficient",
            }
        )
    if run and run.compared_count and run.agreed_count < run.compared_count:
        items.append(
            {
                "tone": "info",
                "text": f"Сверка с разметкой исследования: {run.agreed_count} из {run.compared_count}. Расхождения разобраны в методике.",
                "url": reverse("dashboard:methodology"),
            }
        )
    if not items:
        items.append(
            {
                "tone": "ok",
                "text": "Очередь пуста: решения записаны по всем объектам с риском.",
                "url": reverse("dashboard:history"),
            }
        )
    return items


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def overview(request):
    run, outcomes = _current_outcomes()
    per_indicator = indicator_stats(outcomes)
    queue = queue_counts()
    total = Case.objects.count()
    analysed = Case.objects.exclude(attention=Attention.NOT_RUN).count()
    signalled = Case.objects.filter(
        attention__in=[Attention.HIGH, Attention.MEDIUM, Attention.LOW]
    ).count()
    decided = queue.get("confirmed", 0) + queue.get("not_confirmed", 0)
    last_batch = ImportBatch.objects.first()
    agreement = (
        round(100 * run.agreed_count / run.compared_count) if run and run.compared_count else None
    )
    chart_structure = [
        {
            "label": f"{row['indicator'].code_display} — {row['indicator'].short}",
            "value": row["triggered"],
            "color": CATEGORY_COLOURS[i % len(CATEGORY_COLOURS)],
        }
        for i, row in enumerate(per_indicator)
    ]
    chart_bars = [
        {
            "label": row["indicator"].code_display,
            "value": row["triggered"],
            "unit": "срабатываний",
            "url": reverse("dashboard:case_list") + f"?indicator={row['indicator'].code}",
        }
        for row in per_indicator
    ]
    chart_funnel = [
        {"label": "Записи таблиц", "value": Record.objects.count()},
        {"label": "Объекты", "value": total},
        {"label": "Проверены правилами", "value": analysed},
        {"label": "Выявлены сигналы", "value": signalled},
    ]
    return render(
        request,
        "dashboard/overview.html",
        {
            "run": run,
            "total_cases": total,
            "queue": queue,
            "decided": decided,
            "last_batch": last_batch,
            "agreement": agreement,
            "per_indicator": per_indicator,
            "recommendations": recommendations(queue, per_indicator, run),
            "chart_structure": chart_structure,
            "chart_bars": chart_bars,
            "chart_funnel": chart_funnel,
        },
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def analytics(request):
    run, outcomes = _current_outcomes()
    registry = reverse("dashboard:case_list")
    rows = indicator_stats(outcomes)
    for row in rows:
        row["risk_label"] = Risk(row["indicator"].risk).label
        row["url"] = f"{registry}?indicator={row['indicator'].code}"
    bars = [
        {
            "label": row["indicator"].code_display,
            "value": row["triggered"],
            "unit": "сработало",
            "url": row["url"],
        }
        for row in rows
    ]
    return render(
        request,
        "dashboard/analytics.html",
        {"run": run, "per_indicator": rows, "chart_bars": bars},
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def history(request):
    """The event feed grouped by day, with a filter by event kind."""
    events = recent_events()
    counts = Counter(event["kind"] for event in events)
    kind = request.GET.get("kind", "")
    if kind in HISTORY_KINDS:
        events = [event for event in events if event["kind"] == kind]
    else:
        kind = ""
    today = timezone.localdate()
    days = []
    for day, items in groupby(events, key=lambda event: timezone.localtime(event["when"]).date()):
        label = {0: "Сегодня", 1: "Вчера"}.get((today - day).days, "")
        days.append({"date": day, "label": label, "events": list(items)})
    tabs = [{"kind": "", "label": "Все", "count": sum(counts.values())}] + [
        {"kind": key, "label": label, "count": counts[key]} for key, label in HISTORY_KINDS.items()
    ]
    return render(request, "dashboard/history.html", {"days": days, "tabs": tabs, "kind": kind})


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def search_index(request):
    """Everything the search palette can find, in one small JSON document."""
    items = []
    for case in Case.objects.all():
        items.append(
            {
                "group": "object",
                "title": case.cadastral_number or case.title,
                "note": case.get_attention_display().lower()
                if case.attention != Attention.NOT_RUN
                else "открыть",
                "url": reverse("dashboard:case_detail", args=[case.pk]),
                "search": " ".join(
                    [case.title, case.reference, case.cadastral_number, case.address, case.region]
                ).lower(),
            }
        )
    for batch in ImportBatch.objects.all():
        items.append(
            {
                "group": "document",
                "title": batch.file_name,
                "note": f"таблица {batch.indicator_display}",
                "url": reverse("imports:batch", args=[batch.pk]),
                "search": f"{batch.file_name} {batch.indicator_display} таблица".lower(),
            }
        )
    if request.user.has_perm("cases.view_evidence"):
        for evidence in Evidence.objects.select_related("case"):
            items.append(
                {
                    "group": "document",
                    "title": evidence.title,
                    "note": (evidence.case.cadastral_number if evidence.case else "")
                    or evidence.document_type.lower()
                    or "документ",
                    "url": evidence_url(evidence),
                    "search": " ".join(
                        [
                            evidence.title,
                            evidence.case.title if evidence.case else "",
                            evidence.document_type,
                            evidence.source_reference,
                            evidence.description,
                            "документ",
                        ]
                    ).lower(),
                }
            )
    for event in recent_events(40):
        items.append(
            {
                "group": "event",
                "title": event["title"],
                "note": timezone.localtime(event["when"]).strftime("%d.%m.%Y"),
                "url": event["url"],
                "search": f"{event['title']} {event['text']}".lower(),
            }
        )
    actions = [{"title": "Открыть реестр объектов", "url": reverse("dashboard:case_list")}]
    if request.user.has_perm("cases.add_evidence"):
        actions.append({"title": "Загрузить документ", "url": "#upload"})
    if request.user.has_perm("cases.import_cases"):
        actions.append({"title": "Загрузить таблицу", "url": reverse("imports:upload")})
    actions.append({"title": "Как работать с сервисом", "url": reverse("dashboard:methodology")})
    return JsonResponse(
        {"items": items, "actions": actions}, json_dumps_params={"ensure_ascii": False}
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def cases(request):
    from urllib.parse import urlencode

    from cases.models import ReviewOutcome

    filters = _filters(request)
    objects = case_list(**filters)
    page = Paginator(objects, 25).get_page(request.GET.get("page"))
    ids = [case.pk for case in page]
    reviews = latest_reviews(ids)
    query_string = request.GET.copy()
    query_string.pop("page", None)

    # indicators of each listed object: the triggered ones carry the indicator's risk colour
    checked = {}
    for case_id, code in Record.cases.through.objects.filter(case_id__in=ids).values_list(
        "case_id", "record__indicator"
    ):
        checked.setdefault(case_id, set()).add(code)
    rank = {"high": 0, "medium": 1, "low": 2}
    chips = {}
    for case in page:
        triggered = set(case.triggered_list)
        codes = [code for code in checked.get(case.pk, set()) | triggered if code in INDICATORS]
        codes.sort(
            key=lambda code: (
                code not in triggered,
                rank.get(INDICATORS[code].risk, 3),
                int(code[1:]),
            )
        )
        chips[case.pk] = [
            {
                "code": INDICATORS[code].code_display,
                "short": INDICATORS[code].short,
                "risk": INDICATORS[code].risk if code in triggered else "",
            }
            for code in codes
        ]

    # tabs: risk keeps the objects without a final decision, decisions take the decided ones
    queue = queue_counts()
    keep = {
        key: value
        for key, value in (
            ("q", filters["query"]),
            ("indicator", filters["indicator"]),
            ("region", filters["region"]),
        )
        if value
    }

    def tab(label, count, attention="", review=""):
        params = {**keep, **({"attention": attention} if attention else {})}
        if review:
            params["review"] = review
        current = filters["attention"] == attention and filters["review"] == review
        return {
            "label": label,
            "count": count,
            "attention": attention,
            "review": review,
            "url": request.path + ("?" + urlencode(params) if params else ""),
            "current": current,
        }

    tabs = [tab("Все", Case.objects.count())]
    tabs += [
        tab(label, queue.get(value, 0), attention=value)
        for value, label in (
            (Attention.HIGH, "Высокий"),
            (Attention.MEDIUM, "Средний"),
            (Attention.LOW, "Низкий"),
            (Attention.INSUFFICIENT, "Нет данных"),
        )
    ]
    tabs += [
        tab(choice.label, queue.get(choice.value, 0), review=choice.value)
        for choice in (ReviewOutcome.CONFIRMED, ReviewOutcome.NOT_CONFIRMED)
    ]
    return render(
        request,
        "dashboard/case_list.html",
        {
            "page_obj": page,
            "registry_documents": Evidence.objects.filter(case__isnull=True)[:30]
            if request.user.has_perm("cases.view_evidence")
            else [],
            "filters": filters,
            "query_string": query_string.urlencode(),
            "reviews": reviews,
            "chips": chips,
            "tabs": tabs,
            "indicators": INDICATORS.values(),
            "regions": Case.objects.exclude(region="")
            .order_by("region")
            .values_list("region", flat=True)
            .distinct(),
            "review_choices": REVIEW_FILTERS.items(),
            "run": AnalysisRun.objects.first(),
        },
    )


RISK_WORD = {
    Attention.HIGH: "Высокий",
    Attention.MEDIUM: "Средний",
    Attention.LOW: "Низкий",
    Attention.INSUFFICIENT: "Нет данных",
    Attention.NONE: "Нет сигналов",
    Attention.NOT_RUN: "Нет анализа",
}


def _card_view(request):
    """«Сводка» or «Граф»: the switch at the bottom of the card; a review form keeps it."""
    return (
        "graph" if (request.POST.get("view") or request.GET.get("view")) == "graph" else "summary"
    )


def detail_context(request, case, form=None):
    records = case.records.all()
    story = case_story(case, latest_outcomes(records))
    reviews = (
        list(case.reviews.select_related("author"))
        if request.user.has_perm("cases.view_review")
        else []
    )
    evidence = list(case.evidence.all()) if request.user.has_perm("cases.view_evidence") else []
    statuses = Counter(item["outcome"].status for item in story["findings"] if item["outcome"])
    count = len(story["findings"])
    return {
        "case": case,
        "story": story,
        "graph": case_graph(story, reviews),
        "view": _card_view(request),
        "risk_word": RISK_WORD.get(case.attention, case.get_attention_display()),
        "kpi": {
            "checked": sum(statuses.values()),
            "triggered": statuses[RuleStatus.TRIGGERED],
            "insufficient": statuses[RuleStatus.INSUFFICIENT_DATA],
            "documents": len(evidence) + len(story["documents"]),
        },
        # circles take as many columns as there are indicators: 3 to 5, six and more in rows of 3–4
        "indicator_cols": count if 3 <= count <= 5 else (3 if count < 3 or count in (6, 9) else 4),
        "outline": svg_outline(case.geometry),
        "grid": range(0, 241, 30),
        "review_form": form if form is not None else ReviewForm(),
        "reviews": reviews,
        "evidence": evidence,
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
        url = reverse("dashboard:case_detail", args=[case.id])
        return redirect(url + "?view=graph" if _card_view(request) == "graph" else url)
    return render(
        request, "dashboard/case_detail.html", detail_context(request, case, form), status=400
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def case_map(request):
    import datetime as dt

    from django.utils.timesince import timesince

    from cases.models import ATTENTION_ORDER

    features, linked_ids = [], []
    for case in Case.objects.filter(geometry__isnull=False):
        features.append(
            {
                "kind": "plot",
                "id": str(case.pk),
                "attention": case.attention,
                "points": case.geometry,
            }
        )
        linked_ids.append(case.pk)
    for record in Record.objects.filter(indicator="I2").prefetch_related("cases"):
        fact = record.facts.get("geometry", {})
        if fact.get("state") != "present":
            continue
        linked = record.cases.first()
        features.append(
            {
                "kind": "zone",
                "id": str(linked.pk) if linked else "",
                "attention": linked.attention if linked else "none",
                "points": parse_wkt_polygon(fact["value"]),
            }
        )
        if linked:
            linked_ids.append(linked.pk)

    # the object column: facts from the object's own records, indicators by their latest
    # outcome, and the object's events from the one feed (decisions, its tables, analysis)
    events = recent_events()
    by_url = {}
    for event in events:
        by_url.setdefault(event["url"], []).append(event)
    analysis = next((event for event in events if event["kind"] == "analysis"), None)
    cases = sorted(
        Case.objects.filter(pk__in=linked_ids).prefetch_related("records__batch"),
        key=lambda case: (
            ATTENTION_ORDER.get(case.attention, 9),
            -case.signal_count,
            case.reference,
        ),
    )
    rank = {"high": 0, "medium": 1, "low": 2}
    objects = []
    for case in cases:
        records = list(case.records.all())
        outcomes = latest_outcomes(records)
        area, category, changed, batches, states = case.area_sq_m, "", None, {}, {}
        for record in records:
            indicator = INDICATORS.get(record.indicator)
            if indicator is None:
                continue
            facts = record.facts
            for column in indicator.columns:
                fact = facts.get(column.key) or {}
                if fact.get("state") != "present":
                    continue
                if column.kind == "date":
                    try:
                        day = dt.date.fromisoformat(fact["value"])
                    except (TypeError, ValueError):
                        continue
                    changed = max(changed, day) if changed else day
                elif (
                    column.key == "area" and area is None and isinstance(fact["value"], int | float)
                ):
                    area = fact["value"]
                elif column.key == "category_after" and not category:
                    category = fact["value"]
            batches[record.batch_id] = record.batch
            outcome = outcomes.get(record.pk)
            status = outcome.status if outcome else RuleStatus.INSUFFICIENT_DATA
            order = {RuleStatus.TRIGGERED: 0, RuleStatus.INSUFFICIENT_DATA: 1}
            previous = states.get(record.indicator)
            if previous is None or order.get(status, 2) < order.get(previous, 2):
                states[record.indicator] = status
        for code in case.triggered_list:
            states[code] = RuleStatus.TRIGGERED
        indicators = []
        for code, status in states.items():
            indicator = INDICATORS.get(code)
            if indicator is None:
                continue
            if status == RuleStatus.TRIGGERED:
                tone = indicator.risk
            elif status == RuleStatus.NOT_TRIGGERED:
                tone = "none"
            else:
                tone = "insufficient"
            indicators.append(
                {"code": indicator.code_display, "short": indicator.short, "tone": tone}
            )
        indicators.sort(key=lambda item: (rank.get(item["tone"], 3), item["code"]))
        detail = reverse("dashboard:case_detail", args=[case.pk])
        history = list(by_url.get(detail, []))
        for batch in batches.values():
            history += by_url.get(reverse("imports:batch", args=[batch.pk]), [])
        history.sort(key=lambda event: event["when"], reverse=True)
        history = history[:3] + ([analysis] if analysis else [])
        history = [
            {**event, "ago": timesince(event["when"], depth=1) + " назад"} for event in history
        ]
        facts = []
        if area:
            facts.append(("i-area", "площадь", f"{round(area):,}".replace(",", " ") + " м²"))
        if changed:
            facts.append(("i-calendar", "последнее изменение", changed.strftime("%d.%m.%Y")))
        if category:
            facts.append(("i-pin", "категория", category))
        objects.append(
            {
                "id": str(case.pk),
                "number": case.cadastral_number or case.reference,
                "kind": " / ".join(part for part in (case.object_kind, case.region) if part),
                "address": case.address,
                "attention": case.attention,
                "attention_label": case.get_attention_display(),
                "facts": facts,
                "indicators": indicators,
                # one row of circles up to five, then even rows: 6 → 3 + 3, 7 → 4 + 3
                "columns": {6: 3}.get(len(indicators), min(max(len(indicators), 4), 5))
                if len(indicators) <= 6
                else 4,
                "history": history,
                "url": detail,
            }
        )
    without = Case.objects.filter(geometry__isnull=True).count()
    center = (
        centroid([feature["points"][0] for feature in features]) if features else [47.23, 39.72]
    )
    return render(
        request,
        "dashboard/map.html",
        {
            "features": features,
            "objects": objects,
            "selected": objects[0]["id"] if objects else "",
            "without_geometry": without,
            "center": center,
        },
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
    repeating = [
        person
        for person in people
        if person["outcome"] and person["outcome"].status == RuleStatus.TRIGGERED
    ]
    return render(
        request,
        "dashboard/officials.html",
        {
            "people": people,
            "repeating": len(repeating),
            "episodes": sum(len(person["episodes"]) for person in people),
            "linked_cases": len({case.pk for person in people for case in person["cases"]}),
        },
    )


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def sources(request):
    latest = {}
    for batch in ImportBatch.objects.select_related("uploaded_by"):
        latest.setdefault(batch.indicator, batch)
    batches = sorted(latest.values(), key=lambda batch: int(batch.indicator[1:]))
    return render(
        request,
        "dashboard/sources.html",
        {
            "sources": sources_with_usage(batches),
            "batches": [(INDICATORS.get(batch.indicator), batch) for batch in batches],
            "records": Record.objects.count(),
        },
    )


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
    weights = [
        {
            "level": level.value,
            "label": level.label,
            "indicators": [item for item in INDICATORS.values() if item.risk == level.value],
        }
        for level in Risk
    ]
    return render(
        request,
        "dashboard/methodology.html",
        {"run": run, "rows": rows, "status_labels": STATUS_LABELS, "weights": weights},
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
