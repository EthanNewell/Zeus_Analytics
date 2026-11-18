import datetime as dt

from django import template

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
        text = f"{value:,.2f}".rstrip("0").rstrip(".") if not float(value).is_integer() else f"{int(value):,}"
        return text.replace(",", " ").replace(".", ",")
    if kind == "points":
        return f"контур, {value.count(';') + 1} точек"
    if kind == "wkt":
        return f"полигон зоны, {value.count(',') } точек"
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
