"""Read models for the registry, the card, the map and the summary."""

import datetime as dt

from django.db.models import Q

from .facts import PRESENT, date_in_text
from .indicators import INDICATORS
from .models import Attention, Case, Review, ReviewOutcome

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
        cases = cases.filter(attention=attention)
    if indicator in INDICATORS:
        cases = cases.filter(records__indicator=indicator).distinct()
    if region:
        cases = cases.filter(region=region)
    if review == "none":
        cases = cases.filter(reviews__isnull=True)
    elif review in ReviewOutcome.values:
        latest = {}
        for case_id, outcome in Review.objects.order_by("case_id", "-created_at").values_list(
            "case_id", "outcome"
        ):
            latest.setdefault(case_id, outcome)
        cases = cases.filter(pk__in=[pk for pk, value in latest.items() if value == review])
    return cases


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
    order = {"triggered": 0, "insufficient_data": 1, "not_triggered": 2, "not_applicable": 3}
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
