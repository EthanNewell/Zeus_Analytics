"""Versioned indicator rules. One rule per indicator code from cases.indicators.

A rule reads only input facts (never the calculated columns of the source table) and
returns a status, a priority, an explanation, the facts it used and what is missing.
"""

from dataclasses import dataclass, field

from cases.facts import (
    ABSENT,
    PRESENT,
    add_months,
    fact_date,
    fact_state,
    fact_value,
    normalize_header,
    parse_points,
    text_starts_yes,
)
from cases.geometry import shape_metrics
from cases.indicators import INDICATORS

from ..contracts import Priority, RuleStatus

FILL_THRESHOLD = 0.85
SHARE_THRESHOLD = 0.80
WINDOW_MONTHS = 12


@dataclass
class Evaluation:
    status: RuleStatus
    priority: Priority
    explanation: str
    used: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    metrics: list = field(default_factory=list)


def d(value):
    return value.strftime("%d.%m.%Y") if value else "—"


def money(value):
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def number(value, digits=0):
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def _label(code, key):
    return INDICATORS[code].column(key).header


def _missing(code, facts, keys):
    return [_label(code, key) for key in keys if fact_state(facts, key) != PRESENT]


def _insufficient(code, missing, used, what):
    return Evaluation(
        RuleStatus.INSUFFICIENT_DATA,
        Priority.LOW,
        f"Нельзя проверить {what}: не хватает сведений — {', '.join(m.lower() for m in missing)}.",
        used=used,
        missing=missing,
    )


def rule_i1(facts):
    used = ["right_date", "category_change_date"]
    missing = _missing("I1", facts, used)
    if missing:
        return _insufficient("I1", missing, used, "срок между покупкой и сменой категории")
    bought, changed = fact_date(facts, "right_date"), fact_date(facts, "category_change_date")
    days = (changed - bought).days
    window_end = add_months(bought, WINDOW_MONTHS)
    metrics = [("Дней от регистрации права до смены категории", number(days))]
    if changed < bought:
        return Evaluation(
            RuleStatus.NOT_TRIGGERED,
            Priority.LOW,
            f"Категория изменена {d(changed)}, раньше регистрации права {d(bought)}: участок куплен уже после решения.",
            used,
            metrics=metrics,
        )
    if changed <= window_end:
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.NORMAL,
            f"Право зарегистрировано {d(bought)}, а через {days} дн. ({d(changed)}) категорию изменили — внутри окна {WINDOW_MONTHS} месяцев (до {d(window_end)}).",
            used,
            metrics=metrics,
        )
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        f"Между покупкой ({d(bought)}) и сменой категории ({d(changed)}) прошло {days} дн. — больше окна {WINDOW_MONTHS} месяцев.",
        used,
        metrics=metrics,
    )


def rule_i2(facts):
    used = ["zone_area", "owner_area"]
    missing = _missing("I2", facts, used)
    if missing:
        return _insufficient(
            "I2", missing, used, "долю основного владельца в изменённой зоне (сведения — в приложении к акту)"
        )
    zone, owner = fact_value(facts, "zone_area"), fact_value(facts, "owner_area")
    if not zone:
        return _insufficient("I2", [_label("I2", "zone_area")], used, "долю владельца: площадь зоны равна нулю")
    share = owner / zone
    metrics = [("Доля основного владельца в зоне", f"{number(share * 100, 1)} %")]
    after = fact_value(facts, "zone_after") or "новую зону"
    if share >= SHARE_THRESHOLD:
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.NORMAL,
            f"Участки одного владельца занимают {number(owner, 1)} из {number(zone, 1)} га изменённой зоны ({number(share * 100)} %) — зону перевели в «{after}» практически под него.",
            used + ["zone_before", "zone_after", "holders_approval"],
            metrics=metrics,
        )
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        f"Основной владелец занимает {number(share * 100)} % зоны — изменение затрагивает многих правообладателей, порог {number(SHARE_THRESHOLD * 100)} % не достигнут.",
        used,
        metrics=metrics,
    )


def rule_i3(facts):
    used = ["ks_before", "ks_after", "category_change_date", "ks_after_start", "resale_date"]
    missing = _missing("I3", facts, used[:4])
    if missing or fact_state(facts, "resale_date") not in (PRESENT, ABSENT):
        if fact_state(facts, "resale_date") not in (PRESENT, ABSENT):
            missing.append(_label("I3", "resale_date"))
        return _insufficient("I3", missing, used, "выгоду от смены категории")
    before, after = fact_value(facts, "ks_before"), fact_value(facts, "ks_after")
    changed, applied = fact_date(facts, "category_change_date"), fact_date(facts, "ks_after_start")
    growth_after_change = after > before and applied >= changed
    metrics = [("Изменение КС", money(after - before))]
    if before:
        metrics.append(("Рост КС", f"в {number(after / before, 1)} раза"))
    if fact_state(facts, "resale_date") == ABSENT:
        return Evaluation(
            RuleStatus.NOT_TRIGGERED,
            Priority.LOW,
            "Продажи после смены категории не было"
            + (" — выгода не реализована." if growth_after_change else ", рост КС после смены категории не выявлен."),
            used,
            metrics=metrics,
        )
    sold = fact_date(facts, "resale_date")
    if growth_after_change and sold >= changed:
        price = fact_value(facts, "deal_price")
        price_text = f" за {money(price)}" if isinstance(price, int | float) else ""
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.LOW,
            f"После смены категории ({d(changed)}) кадастровая стоимость выросла с {money(before)} до {money(after)}, а {d(sold)} участок продан{price_text}. Контекстный признак: показывает, как могла быть получена выгода.",
            used + ["new_holder", "deal_price"],
            metrics=metrics,
        )
    reason = (
        "кадастровая стоимость выросла до смены категории (переоценка)"
        if not growth_after_change
        else "продажа была раньше смены категории"
    )
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        f"Продажа {d(sold)} была, но {reason} — выгоды именно от смены категории не видно.",
        used,
        metrics=metrics,
    )


def rule_i4(facts):
    used = ["participants", "bypass", "start_price", "final_price"]
    participants = fact_value(facts, "participants")
    bypass = fact_value(facts, "bypass")
    if participants == 1:
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.NORMAL,
            f"Торги с единственным участником: имущество передано по начальной цене {money(fact_value(facts, 'final_price') or 0)} без конкуренции.",
            used + ["counterparty", "method"],
        )
    if bypass:
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.NORMAL,
            f"Признаки обхода обязательных условий: {bypass}",
            used + ["counterparty", "method"],
        )
    start, final = fact_value(facts, "start_price"), fact_value(facts, "final_price")
    if isinstance(start, int | float) and isinstance(final, int | float) and final > start:
        return Evaluation(
            RuleStatus.NOT_TRIGGERED,
            Priority.LOW,
            f"Цена на торгах выросла с {money(start)} до {money(final)} ({number(final / start * 100 - 100)} %) — конкуренция была.",
            used,
            metrics=[("Рост цены на торгах", f"{number(final / start * 100 - 100)} %")],
        )
    if fact_state(facts, "participants") != PRESENT and fact_state(facts, "participants") != ABSENT:
        return _insufficient("I4", [_label("I4", "participants")], used, "конкуренцию на торгах")
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        "Участников больше одного, признаков обхода обязательных условий не выявлено.",
        used,
    )


def rule_i6(facts):
    used = ["purchase_date", "procedure_start", "official", "inn_match", "surname_match"]
    missing = _missing("I6", facts, ["purchase_date", "procedure_start"])
    if missing:
        return _insufficient("I6", missing, used, "очерёдность покупки и процедуры")
    bought, started = fact_date(facts, "purchase_date"), fact_date(facts, "procedure_start")
    days = (started - bought).days
    metrics = [("Дней от покупки до начала процедуры", number(days))]
    if days <= 0:
        return Evaluation(
            RuleStatus.NOT_TRIGGERED,
            Priority.LOW,
            f"Покупка ({d(bought)}) — после начала процедуры ({d(started)}): заранее о решении знать было не нужно.",
            used,
            metrics=metrics,
        )
    if fact_state(facts, "inn_match") != PRESENT:
        return _insufficient(
            "I6", [_label("I6", "inn_match")], used, "связь покупателя с должностным лицом"
        )
    official = (fact_value(facts, "official") or "").split(",")[0]
    if text_starts_yes(fact_value(facts, "inn_match")):
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.HIGH,
            f"Участок куплен {d(bought)}, за {days} дн. до начала процедуры ({d(started)}). В решении участвовал {official}, связь с покупателем подтверждена по ИНН в ЕГРЮЛ: {fact_value(facts, 'inn_match').split('—', 1)[-1].strip()}",
            used + ["buyer", "founders", "procedure"],
            metrics=metrics,
        )
    if text_starts_yes(fact_value(facts, "surname_match")):
        return Evaluation(
            RuleStatus.INSUFFICIENT_DATA,
            Priority.NORMAL,
            f"Покупка за {days} дн. до процедуры, с участником решения ({official}) совпадает только фамилия. Это гипотеза, а не связь: нужна проверка документами.",
            used + ["buyer"],
            missing=["Документальное подтверждение связи (ЕГРЮЛ, анкета, сведения ЗАГС)"],
            metrics=metrics,
        )
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        f"Покупка за {days} дн. до процедуры, но связь покупателя с участником решения ({official}) не выявлена.",
        used,
        metrics=metrics,
    )


def rule_i8(facts):
    used = ["coords"]
    if fact_state(facts, "coords") != PRESENT:
        return _insufficient("I8", [_label("I8", "coords")], used, "форму границ")
    shape = shape_metrics(parse_points(fact_value(facts, "coords")))
    fill = shape["fill"]
    metrics = [
        ("Площадь по координатам", f"{number(shape['area'])} м²"),
        ("Описанный прямоугольник", f"{number(shape['rectangle'])} м²"),
        ("Коэффициент заполнения", number(fill, 3)),
    ]
    stated = fact_value(facts, "area")
    if isinstance(stated, int | float) and stated:
        metrics.append(("Расхождение с площадью из таблицы", f"{number((shape['area'] - stated) / stated * 100, 1)} %"))
    if fill < FILL_THRESHOLD:
        shape_text = fact_value(facts, "shape")
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.NORMAL,
            f"Контур заполняет лишь {number(fill * 100)} % описанного прямоугольника (порог {number(FILL_THRESHOLD * 100)} %)"
            + (f": {shape_text[0].lower()}{shape_text[1:]}." if shape_text else ".")
            + " Изломанность границ может указывать на прирезку чужой земли.",
            used + ["shape"],
            metrics=metrics,
        )
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        f"Контур близок к прямоугольнику: заполнение {number(fill * 100)} %, порог {number(FILL_THRESHOLD * 100)} %.",
        used,
        metrics=metrics,
    )


def rule_i10(facts):
    used = ["repeats", "comment"]
    repeats = fact_value(facts, "repeats")
    if not isinstance(repeats, int | float):
        return _insufficient("I10", [_label("I10", "repeats")], used, "повторяемость лица")
    person = fact_value(facts, "person")
    metrics = [("Эпизодов с участием лица", number(repeats))]
    if repeats > 1:
        return Evaluation(
            RuleStatus.TRIGGERED,
            Priority.HIGH,
            f"{person} фигурирует в {number(repeats)} эпизодах других индикаторов — повторяющийся участник решений.",
            used + ["person"],
            metrics=metrics,
        )
    return Evaluation(
        RuleStatus.NOT_TRIGGERED,
        Priority.LOW,
        f"{person} встречается в одном эпизоде — повторяемости нет.",
        used,
        metrics=metrics,
    )


@dataclass(frozen=True)
class Rule:
    code: str
    version: str
    evaluate: object


RULES = {
    rule.code: rule
    for rule in [
        Rule("I1", "1.0", rule_i1),
        Rule("I2", "1.0", rule_i2),
        Rule("I3", "1.0", rule_i3),
        Rule("I4", "1.0", rule_i4),
        Rule("I6", "1.0", rule_i6),
        Rule("I8", "1.0", rule_i8),
        Rule("I10", "1.0", rule_i10),
    ]
}

MARK_STATUS = {
    "да": RuleStatus.TRIGGERED,
    "нет": RuleStatus.NOT_TRIGGERED,
    "нет данных": RuleStatus.INSUFFICIENT_DATA,
    "нет даты": RuleStatus.INSUFFICIENT_DATA,
    "требует проверки": RuleStatus.INSUFFICIENT_DATA,
    "1 — аномалия": RuleStatus.TRIGGERED,
    "0 — норма": RuleStatus.NOT_TRIGGERED,
}


def expected_status(mark):
    """The research author's answer for a row, in rule statuses; "" when unknown."""
    status = MARK_STATUS.get(normalize_header(mark))
    return status.value if status else ""
