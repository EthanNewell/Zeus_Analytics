"""Value parsing and reading helpers shared by import, analysis and the card.

Every imported cell becomes a fact: {"value", "state", "origin", "cell", "label"}.
"""

import datetime as dt
import math
import re

PRESENT, MISSING, ABSENT = "present", "missing", "absent"

MISSING_TOKENS = {"", "нет данных", "нет даты", "н/д", "нд", "n/a", "na"}
ABSENT_TOKENS = {"—", "–", "-", "нет события", "не применимо"}

CADASTRAL_RE = re.compile(r"\b(\d{2}):(\d{2}):(\d{6,7}):(\d{1,6})\b")
SHORT_RE = re.compile(r"(?<![\d:])[:](\d{1,6})\b")
RANGE_RE = re.compile(r"\b(\d{2}:\d{2}:\d{6,7}):(\d{1,6})\s*[–—-]\s*(?:\1)?:(\d{1,6})\b")
DATE_IN_TEXT_RE = re.compile(r"\bот\s+(\d{2})\.(\d{2})\.(\d{4})\b")
HEADER_SPACE_RE = re.compile(r"\s+")

REGION_BY_CODE = {
    "23": "Краснодарский край",
    "31": "Белгородская обл.",
    "33": "Владимирская обл.",
    "36": "Воронежская обл.",
    "50": "Московская обл.",
    "52": "Нижегородская обл.",
    "61": "Ростовская обл.",
    "64": "Саратовская обл.",
    "66": "Свердловская обл.",
    "74": "Челябинская обл.",
    "76": "Ярославская обл.",
}


COMPARISON_RE = re.compile(r"<=|>=|[≤≥<>?]")


def normalize_header(text):
    """Header key: case, «ё», spaces and comparison signs do not matter.

    «≤»/«≥» are lost as «?» when Excel saves CSV in cp1251, so they compare as one sign.
    """
    text = str(text or "").replace("ё", "е").replace("Ё", "Е").replace("\u00a0", " ")
    text = COMPARISON_RE.sub("~", text)
    return HEADER_SPACE_RE.sub(" ", text).strip().lower()


def classify_text(value):
    """Return (state, cleaned value) for a raw cell value."""
    if value is None:
        return MISSING, None
    if isinstance(value, float) and math.isnan(value):
        return MISSING, None
    if isinstance(value, str):
        cleaned = value.strip()
        lowered = cleaned.lower()
        if lowered in MISSING_TOKENS or lowered.startswith("нет данных"):
            return MISSING, None
        if lowered in ABSENT_TOKENS:
            return ABSENT, None
        return PRESENT, cleaned
    return PRESENT, value


def parse_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%Y-%m-%d %H:%M:%S"):
            try:
                return dt.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise ValueError("ожидается дата ДД.ММ.ГГГГ")


def parse_number(value):
    if isinstance(value, bool):
        raise ValueError("ожидается число")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            pass
    raise ValueError("ожидается число")


def to_json_value(kind, value):
    """Convert a present cell value to its JSON form for the given column kind."""
    if kind == "date":
        return parse_date(value).isoformat()
    if kind == "number":
        number = parse_number(value)
        return int(number) if number.is_integer() else number
    if isinstance(value, dt.datetime | dt.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def fact_state(facts, key):
    fact = facts.get(key)
    return fact["state"] if fact else MISSING


def fact_value(facts, key):
    fact = facts.get(key)
    if not fact or fact["state"] != PRESENT:
        return None
    return fact["value"]


def fact_date(facts, key):
    value = fact_value(facts, key)
    return dt.date.fromisoformat(value) if value else None


YES_RE = re.compile(r"^да(?![а-я])")
NO_RE = re.compile(r"^(нет|не)(?![а-я])")


def text_starts_yes(text):
    """«Да — …» is yes; «Данных нет» is not."""
    return bool(text) and bool(YES_RE.match(normalize_header(text)))


def text_starts_no(text):
    """«Нет», «Не выявлено», «не установлены» are an explicit negative answer."""
    return bool(text) and bool(NO_RE.match(normalize_header(text)))


def add_months(date, months):
    month = date.month - 1 + months
    year = date.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if _leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return dt.date(year, month, min(date.day, days_in_month[month - 1]))


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def cadastral_numbers(text, expand_limit=50):
    """Full cadastral numbers in reading order; expands «:1543, :1544» and «:3352 – :3356».

    A range needs a colon after the dash («:3356» or the full number of the same quarter),
    so «:40 – 61:01:…» or «:5 — 12.03.2023» are never read as ranges.
    """
    if not text:
        return []
    text = str(text)
    events, spans = [], []
    for match in RANGE_RE.finditer(text):
        prefix, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        values = range(start, end + 1) if 0 < end - start <= expand_limit else (start, end)
        events.append((match.start(), [f"{prefix}:{value}" for value in values]))
        spans.append((match.start(), match.end()))
    last_prefix = None
    position = 0
    tokens = sorted(
        [(m.start(), "full", m) for m in CADASTRAL_RE.finditer(text)]
        + [(m.start(), "short", m) for m in SHORT_RE.finditer(text)],
        key=lambda item: item[0],
    )
    for start, kind, match in tokens:
        inside = any(begin <= start < end for begin, end in spans)
        if kind == "full":
            last_prefix = ":".join(match.groups()[:3])
            if not inside and start >= position:
                events.append((start, [match.group(0)]))
                position = match.end()
        elif last_prefix and not inside and start >= position:
            events.append((start, [f"{last_prefix}:{match.group(1)}"]))
    found = []
    for _, numbers in sorted(events, key=lambda item: item[0]):
        for number in numbers:
            if number not in found:
                found.append(number)
    return found


def region_for(cadastral_number, address=""):
    if cadastral_number:
        region = REGION_BY_CODE.get(cadastral_number.split(":")[0])
        if region:
            return region
    for region in REGION_BY_CODE.values():
        stem = region.split()[0][:-2]
        if stem and stem in (address or ""):
            return region
    return ""


def date_in_text(text):
    match = DATE_IN_TEXT_RE.search(text or "")
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def parse_points(text):
    """«lat lon; lat lon» → [[lat, lon], ...]."""
    points = []
    for part in str(text).split(";"):
        part = part.strip()
        if not part:
            continue
        lat, lon = (float(value) for value in part.replace(",", " ").split())
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("координаты вне диапазона WGS-84")
        points.append([lat, lon])
    if len({tuple(point) for point in points}) < 3:
        raise ValueError("нужно не меньше трёх разных точек контура")
    area = sum(
        points[i][1] * points[i - 1][0] - points[i - 1][1] * points[i][0]
        for i in range(len(points))
    )
    if area == 0:
        raise ValueError("контур без площади: точки лежат на одной линии")
    return points


def parse_wkt_polygon(text):
    """POLYGON((lon lat, ...)) → [[lat, lon], ...] without the closing point."""
    match = re.search(r"POLYGON\s*\(\((.+?)\)\)", str(text), re.IGNORECASE)
    if not match:
        raise ValueError("ожидается WKT POLYGON((долгота широта, ...))")
    points = []
    for pair in match.group(1).split(","):
        lon, lat = (float(value) for value in pair.split())
        points.append([lat, lon])
    if len(points) > 3 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise ValueError("нужно не меньше трёх точек контура")
    return points
