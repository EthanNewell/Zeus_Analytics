"""Read models for the registry, the card, the map and the summary."""

import datetime as dt

from django.db.models import Q

from .facts import PRESENT, date_in_text
from .indicators import INDICATORS
from .models import DECIDED, Attention, Case, Evidence, Review, ReviewOutcome

REVIEW_FILTERS = {
    "none": "Без проверки",
    **{choice.value: choice.label for choice in ReviewOutcome},
}


def case_list(query="", attention="", indicator="", region="", review=""):
    cases = Case.objects.all()
    if query:
        cases = cases.filter(
            Q(reference__icontains=query)
            | Q(title__icontains=query)
            | Q(cadastral_number__icontains=query)
            | Q(address__icontains=query)
            | Q(records__title__icontains=query)
        ).distinct()
    if attention in Attention.values:
        decided = [pk for pk, value in latest_outcome_by_case().items() if value in DECIDED]
        cases = cases.filter(attention=attention).exclude(pk__in=decided)
    if indicator in INDICATORS:
        cases = cases.filter(records__indicator=indicator).distinct()
    if region:
        cases = cases.filter(region=region)
    if review == "none":
        cases = cases.filter(reviews__isnull=True)
    elif review in ReviewOutcome.values:
        latest = latest_outcome_by_case()
        cases = cases.filter(pk__in=[pk for pk, value in latest.items() if value == review])
    return cases


def latest_outcome_by_case():
    """{case id: outcome of its newest review}."""
    latest = {}
    for case_id, outcome in Review.objects.order_by("case_id", "-created_at").values_list(
        "case_id", "outcome"
    ):
        latest.setdefault(case_id, outcome)
    return latest


def latest_reviews(case_ids):
    latest = {}
    for review in (
        Review.objects.filter(case_id__in=case_ids)
        .select_related("author")
        .order_by("case_id", "-created_at")
    ):
        latest.setdefault(review.case_id, review)
    return latest


def case_story(case, outcomes_by_record):
    """Everything the card shows, assembled from the case's records."""
    records = list(case.records.select_related("batch").order_by("indicator", "row_number"))
    findings, timeline, parties, documents, fact_tables = [], [], [], [], []
    seen_parties, seen_documents = {}, set()
    for record in records:
        indicator = INDICATORS.get(record.indicator)
        if indicator is None:
            continue
        outcome = outcomes_by_record.get(record.pk)
        findings.append({"record": record, "indicator": indicator, "outcome": outcome})
        rows = []
        for column in indicator.columns:
            fact = record.facts.get(column.key)
            if not fact or column.key == "number":
                continue
            used = bool(outcome and column.key in outcome.used_fields)
            rows.append({"column": column, "fact": fact, "used": used})
            if fact["state"] != PRESENT:
                continue
            value = fact["value"]
            if column.timeline:
                when = None
                if column.kind == "date":
                    when = dt.date.fromisoformat(value)
                else:
                    when = date_in_text(value)
                if when:
                    timeline.append(
                        {
                            "date": when,
                            "label": column.timeline,
                            "detail": value if column.kind != "date" else "",
                            "indicator": indicator,
                            "origin": fact["origin"],
                        }
                    )
            if column.party:
                key = _party_key(value)
                if key in seen_parties:
                    party = seen_parties[key]
                    if column.party not in party["roles"]:
                        party["roles"].append(column.party)
                    if len(value) > len(party["value"]):
                        party["value"] = value
                else:
                    seen_parties[key] = {
                        "roles": [column.party],
                        "value": value,
                        "origin": fact["origin"],
                    }
                    parties.append(seen_parties[key])
            if column.document and value not in seen_documents:
                seen_documents.add(value)
                documents.append(
                    {
                        "label": column.header,
                        "value": value,
                        "origin": fact["origin"],
                        "indicator": indicator,
                        "record": record,
                    }
                )
        fact_tables.append(
            {"record": record, "indicator": indicator, "rows": rows, "outcome": outcome}
        )
    unique_timeline = {}
    for event in timeline:
        unique_timeline.setdefault((event["date"], event["label"]), event)
    findings.sort(key=_finding_rank)
    return {
        "findings": findings,
        "timeline": sorted(unique_timeline.values(), key=lambda event: event["date"]),
        "parties": parties,
        "documents": documents,
        "fact_tables": fact_tables,
        "sources": _source_names(record.batch.sources_note for record in records),
    }


def _finding_rank(item):
    outcome = item["outcome"]
    code = int(item["indicator"].code[1:])
    if outcome is None:
        return (9, 9, code)
    order = {"triggered": 0, "insufficient_data": 1, "not_triggered": 2}
    priority = {"high": 0, "normal": 1, "low": 2}
    return (order.get(outcome.status, 5), priority.get(outcome.priority, 5), code)


def _party_key(value):
    return value.split(", ИНН")[0].split("\n")[0].strip().lower()


def _source_names(notes):
    """«Источники данных: НСПД, Росреестр (…), …» from several tables → one deduplicated list."""
    names = []
    for note in notes:
        if not note:
            continue
        text = note.split(":", 1)[-1].strip().rstrip(".")
        depth, current = 0, ""
        for char in text + ",":
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char == "," and depth == 0:
                name = current.strip()
                if name and name not in names:
                    names.append(name)
                current = ""
            else:
                current += char
    return names


def svg_outline(points, size=240, pad=16):
    """Contour as an SVG path scaled into a square, north up; None without geometry."""
    if not points or len(points) < 3:
        return None
    import math

    lat0 = sum(lat for lat, _ in points) / len(points)
    scale_x = math.cos(math.radians(lat0))
    xy = [(lon * scale_x, -lat) for lat, lon in points]
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1
    inner = size - 2 * pad
    offset_x = pad + (inner - (max(xs) - min(xs)) / span * inner) / 2
    offset_y = pad + (inner - (max(ys) - min(ys)) / span * inner) / 2
    coords = [
        (offset_x + (x - min(xs)) / span * inner, offset_y + (y - min(ys)) / span * inner)
        for x, y in xy
    ]
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in coords) + " Z"


def evidence_url(evidence):
    """Where a document opens: its object's card, or the file itself when it has no object."""
    from django.urls import reverse

    if evidence.case_id:
        return reverse("dashboard:case_detail", args=[evidence.case_id]) + "#documents"
    if evidence.file:
        return reverse("dashboard:evidence_download", args=[evidence.id])
    return evidence.url or reverse("dashboard:history")


def recent_events(limit=None):
    """The one event feed: reviews, uploads (tables and documents) and analysis runs, newest first.

    Feeds the bell, the «История изменений» page and the search palette. Each event is a dict:
    kind, tone (high | medium | ok | info), title, text, when, url.
    """
    from django.urls import reverse

    from analysis.models import AnalysisRun
    from imports.models import ImportBatch

    tone = {
        ReviewOutcome.CONFIRMED: "high",
        ReviewOutcome.NOT_CONFIRMED: "ok",
        ReviewOutcome.NEEDS_INFORMATION: "info",
    }
    events = []
    for review in Review.objects.select_related("author", "case").order_by("-created_at")[:50]:
        events.append(
            {
                "kind": "review",
                "tone": tone.get(review.outcome, "info"),
                "title": f"{review.author.username}: «{review.get_outcome_display()}»",
                "text": f"{review.case.title}. {review.comment}"[:220],
                "when": review.created_at,
                "url": reverse("dashboard:case_detail", args=[review.case_id]),
            }
        )
    for batch in ImportBatch.objects.select_related("uploaded_by").order_by("-created_at")[:50]:
        events.append(
            {
                "kind": "import",
                "tone": "info",
                "title": f"Загружена таблица {batch.indicator_display}",
                "text": f"{batch.file_name}: строк {batch.rows_total}, новых {batch.rows_created}, обновлено {batch.rows_updated}",
                "when": batch.created_at,
                "url": reverse("imports:batch", args=[batch.id]),
            }
        )
    for evidence in Evidence.objects.select_related("added_by", "case").filter(
        added_at__isnull=False
    )[:50]:
        where = (evidence.case.cadastral_number or evidence.case.title) if evidence.case else ""
        events.append(
            {
                "kind": "import",
                "tone": "info",
                "title": "Загружен документ",
                "text": ", ".join(
                    part for part in (evidence.title, evidence.document_type, where) if part
                )[:220],
                "when": evidence.added_at,
                "url": evidence_url(evidence),
            }
        )
    for run in AnalysisRun.objects.select_related("started_by").order_by("-started_at")[:20]:
        events.append(
            {
                "kind": "analysis",
                "tone": "info",
                "title": "Анализ выполнен",
                "text": f"Записей {run.records_count}, сработало {run.triggered_count}, объектов {run.cases_count}, {run.duration_ms} мс",
                "when": run.started_at,
                "url": reverse("dashboard:analytics"),
            }
        )
    events.sort(key=lambda event: event["when"], reverse=True)
    return events[:limit] if limit else events


def queue_counts():
    """Cases by risk that still wait for a decision, and decided cases by outcome."""
    decided = latest_outcome_by_case()
    counts = {key: 0 for key in Attention.values}
    for pk, attention in Case.objects.values_list("pk", "attention"):
        if decided.get(pk) not in (ReviewOutcome.CONFIRMED, ReviewOutcome.NOT_CONFIRMED):
            counts[attention] += 1
    for outcome in decided.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def _plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# a review outcome as a status dot of the shared «.risk» part
REVIEW_TONE = {
    ReviewOutcome.CONFIRMED: "confirmed",
    ReviewOutcome.NOT_CONFIRMED: "not_confirmed",
    ReviewOutcome.NEEDS_INFORMATION: "needs_information",
}


def case_graph(story, reviews):
    """Nodes of the card's graph, in stage order: object → «сработали N индикаторов» →
    one branch per triggered or data-short indicator → colleagues' comments → the outcome.

    ``reviews`` are the case's Review records in any order; ``story`` is case_story().
    """
    checked = [item for item in story["findings"] if item["outcome"] is not None]
    triggered = [item for item in checked if item["outcome"].status == "triggered"]
    short = [item for item in checked if item["outcome"].status == "insufficient_data"]
    branches = [
        {
            "indicator": item["indicator"],
            "tone": item["indicator"].risk,
            "state": "сработал",
        }
        for item in triggered
    ] + [
        {"indicator": item["indicator"], "tone": "unknown", "state": "нет данных"} for item in short
    ]
    n = len(triggered)
    if n:
        verb = "сработал" if n % 10 == 1 and n % 100 != 11 else "сработали"
        plate = f"{verb} {n} {_plural(n, 'индикатор', 'индикатора', 'индикаторов')}"
    else:
        plate = "индикаторы не сработали"
    comments = sorted(reviews, key=lambda review: review.created_at)
    for review in comments:
        review.tone = REVIEW_TONE.get(review.outcome, "unknown")
    last = comments[-1] if comments else None
    return {
        "plate": plate,
        "checked": len(checked),
        "branches": branches,
        "comments": comments,
        "last": last,
        "decided": bool(last and last.outcome in DECIDED),
    }
