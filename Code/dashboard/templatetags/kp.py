import datetime as dt

from django import template
from django.utils.safestring import mark_safe

from analysis.contracts import RuleStatus
from cases.facts import ABSENT, MISSING
from cases.models import Origin

register = template.Library()

ORIGIN_CLASS = {
    Origin.AUTHOR_MARKED_REAL: "o-real",
    Origin.SYNTHETIC: "o-synth",
    Origin.CALCULATED: "o-calc",
    Origin.UNKNOWN: "o-unknown",
}
ORIGIN_SHORT = {
    Origin.AUTHOR_MARKED_REAL: "реальное",
    Origin.SYNTHETIC: "синтетика",
    Origin.CALCULATED: "расчёт",
    Origin.UNKNOWN: "уточнить",
}
STATUS = {
    RuleStatus.TRIGGERED: ("s-trig", "Сработал"),
    RuleStatus.NOT_TRIGGERED: ("s-none", "Не сработал"),
    RuleStatus.INSUFFICIENT_DATA: ("s-insuf", "Недостаточно данных"),
    RuleStatus.NOT_APPLICABLE: ("s-na", "Не применим"),
}


@register.filter
def origin_class(origin):
    return ORIGIN_CLASS.get(origin, "o-missing")


@register.filter
def origin_short(origin):
    return ORIGIN_SHORT.get(origin, "нет данных")


@register.filter
def status_class(status):
    return STATUS.get(status, ("s-na", ""))[0]


@register.filter
def status_label(status):
    return STATUS.get(status, ("", "—"))[1]


@register.filter
def attention_class(attention):
    return f"a-{attention}"


@register.filter
def fact_display(fact, column=None):
    if not fact:
        return "нет данных"
    if fact.get("state") == MISSING:
        return "нет данных"
    if fact.get("state") == ABSENT:
        return "—"
    value = fact.get("value")
    kind = getattr(column, "kind", "text")
    if kind == "date":
        try:
            return dt.date.fromisoformat(value).strftime("%d.%m.%Y")
        except (TypeError, ValueError):
            return value
    if kind == "number" and isinstance(value, int | float):
        text = (
            f"{value:,.2f}".rstrip("0").rstrip(".")
            if not float(value).is_integer()
            else f"{int(value):,}"
        )
        return text.replace(",", " ").replace(".", ",")
    if kind == "points":
        return f"контур, {value.count(';') + 1} точек"
    if kind == "wkt":
        return f"полигон зоны, {value.count(',')} точек"
    return value


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def percent(part, whole):
    try:
        return round(part / whole * 100)
    except (TypeError, ZeroDivisionError):
        return 0


@register.filter
def code_display(code):
    return "И" + str(code)[1:]


ATTENTION_LEVEL = {"high": 5, "normal": 3, "low": 2, "none": 0, "insufficient": -1, "not_run": -1}


def _level_svg(level):
    cells = []
    for index in range(5):
        if level < 0:
            cells.append(
                f'<rect x="{index * 4 + 0.5}" y="0.5" width="2" height="8" fill="none" stroke="currentColor" stroke-opacity="0.6"/>'
            )
        else:
            opacity = 1 if index < level else 0.22
            cells.append(
                f'<rect x="{index * 4}" y="0" width="3" height="9" fill="currentColor" fill-opacity="{opacity}"/>'
            )
    return mark_safe(
        '<svg class="lv" viewBox="0 0 19 9" width="19" height="9" aria-hidden="true" shape-rendering="crispEdges">'
        + "".join(cells)
        + "</svg>"
    )


@register.simple_tag
def attention_level(attention):
    """Five cells, filled by the case's attention; empty outline means «no data»."""
    return _level_svg(ATTENTION_LEVEL.get(attention, -1))


@register.simple_tag
def outcome_level(outcome):
    if outcome is None:
        return _level_svg(-1)
    if outcome.status == RuleStatus.TRIGGERED:
        return _level_svg({"high": 5, "normal": 3, "low": 2}.get(outcome.priority, 3))
    if outcome.status == RuleStatus.NOT_TRIGGERED:
        return _level_svg(0)
    return _level_svg(-1)
