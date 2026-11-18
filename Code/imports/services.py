"""Import of indicator tables (.xlsx as prepared by the research team, or .csv).

The whole file is parsed and validated before anything is written; a file with any
error leaves no domain data behind. Re-importing updates records by their key.
"""

import csv
import hashlib
import io
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction

from cases.facts import (
    MISSING,
    PRESENT,
    classify_text,
    normalize_header,
    parse_points,
    parse_wkt_polygon,
    region_for,
    to_json_value,
)
from cases.indicators import INDICATORS, detect
from cases.models import Case, Origin, Record

from .contracts import ImportError, ImportResult
from .models import ImportBatch

YELLOW = ("FFFF00",)
HEADER_SEARCH_ROWS = 5


@dataclass
class ParsedRow:
    row_number: int
    facts: dict
    author_mark: str
    key: str
    title: str
    cases: list = field(default_factory=list)


@dataclass
class ParsedTable:
    indicator: object
    sheet: str
    rows: list
    notes: list
    errors: list


def import_table(*, actor, uploaded_file):
    if not actor.is_active or not actor.has_perms(["cases.view_case", "cases.import_cases"]):
        raise PermissionDenied
    if uploaded_file is None:
        return _failed("file", "no_file", "Выберите файл .xlsx или .csv.")
    if uploaded_file.size > settings.MAX_IMPORT_BYTES:
        limit = settings.MAX_IMPORT_BYTES // 1024
        return _failed("file", "too_large", f"Файл больше допустимых {limit} КиБ.")
    content = uploaded_file.read()
    name = uploaded_file.name or "upload"
    lowered = name.lower()
    try:
        if lowered.endswith((".xlsx", ".xlsm")):
            table, file_format = read_xlsx(content), "xlsx"
        elif lowered.endswith((".csv", ".txt")):
            table, file_format = read_csv(content), "csv"
        else:
            return _failed("file", "format", "Поддерживаются файлы .xlsx и .csv.")
    except UnreadableFile as error:
        return _failed("file", "unreadable", str(error))
    if table.errors:
        return ImportResult(batch_id=None, errors=tuple(table.errors))
    return _save(actor, name, content, file_format, table)


class UnreadableFile(Exception):
    pass


def _failed(field_name, code, message):
    return ImportResult(batch_id=None, errors=(ImportError(0, field_name, code, message),))


def read_xlsx(content):
    from openpyxl import load_workbook

    try:
        formulas = load_workbook(io.BytesIO(content), read_only=False, data_only=False)
        values = load_workbook(io.BytesIO(content), read_only=False, data_only=True)
    except Exception as error:  # openpyxl raises many unrelated types for broken files
        raise UnreadableFile("Не удалось прочитать книгу Excel.") from error
    for sheet in formulas.worksheets:
        value_sheet = values[sheet.title]
        grid = []
        for row_cells, value_cells in zip(sheet.iter_rows(), value_sheet.iter_rows(), strict=False):
            grid.append(
                [
                    _xlsx_cell(cell, value)
                    for cell, value in zip(row_cells, value_cells, strict=False)
                ]
            )
        table = _parse_grid(grid, sheet.title, default_origin=Origin.SYNTHETIC)
        if table is not None:
            return table
    return ParsedTable(None, "", [], [], [ImportError(0, "file", "unknown_table", _unknown())])


def _xlsx_cell(cell, value_cell):
    raw = cell.value
    is_formula = isinstance(raw, str) and raw.startswith("=")
    fill = cell.fill
    color = ""
    if fill is not None and fill.fill_type == "solid" and fill.fgColor is not None:
        color = str(fill.fgColor.rgb or "")
    if is_formula:
        origin = Origin.CALCULATED
    elif color.upper().endswith(YELLOW):
        origin = Origin.AUTHOR_MARKED_REAL
    else:
        origin = None  # default for the table
    return {"value": value_cell.value, "origin": origin, "cell": cell.coordinate}


def read_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1251")
        except UnicodeDecodeError as error:
            raise UnreadableFile("Файл CSV должен быть в кодировке UTF-8.") from error
    sample = text[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    grid = []
    for row_index, row in enumerate(reader, start=1):
        grid.append(
            [
                {"value": value, "origin": None, "cell": f"{_column_letter(col)}{row_index}"}
                for col, value in enumerate(row, start=1)
            ]
        )
    table = _parse_grid(grid, "CSV", default_origin=Origin.UNKNOWN)
    if table is None:
        return ParsedTable(None, "", [], [], [ImportError(0, "file", "unknown_table", _unknown())])
    return table


def _column_letter(index):
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _unknown():
    known = ", ".join(item.code_display for item in INDICATORS.values())
    return f"Не найдена строка заголовков ни одной из таблиц индикаторов ({known})."


def _parse_grid(grid, sheet_name, *, default_origin):
    header_index, indicator = None, None
    for index, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
        indicator = detect([cell["value"] for cell in row])
        if indicator:
            header_index = index
            break
    if indicator is None:
        return None
    headers = {
        normalize_header(cell["value"]): position
        for position, cell in enumerate(grid[header_index])
        if cell["value"] not in (None, "")
    }
    errors, rows, notes, seen = [], [], [], {}
    positions = {}
    for column in indicator.columns:
        if column.normalized in headers:
            positions[column.key] = headers[column.normalized]
        elif column.required:
            errors.append(
                ImportError(
                    header_index + 1, column.header, "missing_column", "Нет обязательной колонки."
                )
            )
    if errors:
        return ParsedTable(indicator, sheet_name, [], [], errors)
    for row in grid[header_index + 1 :]:
        filled = [cell for cell in row if cell["value"] not in (None, "")]
        if not filled:
            continue
        if len(filled) == 1 and filled[0] is row[0] and isinstance(row[0]["value"], str):
            notes.append(row[0]["value"].strip())
            continue
        if len(rows) >= settings.MAX_IMPORT_ROWS:
            errors.append(
                ImportError(0, "file", "too_many_rows", f"Больше {settings.MAX_IMPORT_ROWS} строк.")
            )
            break
        parsed = _parse_row(indicator, row, positions, default_origin, errors)
        if parsed is None:
            continue
        if parsed.key in seen:
            errors.append(
                ImportError(
                    parsed.row_number,
                    indicator.column(indicator.key_column).header,
                    "duplicate",
                    f"Запись повторяет строку {seen[parsed.key]}.",
                )
            )
            continue
        seen[parsed.key] = parsed.row_number
        rows.append(parsed)
    if not rows and not errors:
        errors.append(ImportError(0, "file", "empty", "В таблице нет строк с данными."))
    return ParsedTable(indicator, sheet_name, rows, notes, errors)


def _parse_row(indicator, row, positions, default_origin, errors):
    row_number = _row_number(row)
    facts, author_mark, row_errors = {}, "", []
    for column in indicator.columns:
        position = positions.get(column.key)
        if position is None or position >= len(row):
            cell = {"value": None, "origin": None, "cell": ""}
        else:
            cell = row[position]
        state, value = classify_text(cell["value"])
        origin = cell["origin"] or default_origin
        if column.mark:
            author_mark = "" if cell["value"] is None else str(cell["value"]).strip()
            continue
        if state == PRESENT and not column.calculated:
            try:
                value = to_json_value(column.kind, value)
                if column.kind == "points":
                    parse_points(value)
                elif column.kind == "wkt":
                    parse_wkt_polygon(value)
            except ValueError as error:
                row_errors.append(
                    ImportError(row_number, column.header, "invalid_value", str(error))
                )
                continue
        elif state == PRESENT:
            value = to_json_value("text", value)
        if column.required and state != PRESENT:
            row_errors.append(
                ImportError(
                    row_number, column.header, "required", "Обязательное значение не заполнено."
                )
            )
        if state != PRESENT:
            value = None
        facts[column.key] = {
            "value": value,
            "state": state,
            "origin": origin if state != MISSING or cell["origin"] == Origin.CALCULATED else "",
            "cell": cell["cell"],
            "label": column.header,
        }
    if row_errors:
        errors.extend(row_errors)
        return None
    cases = indicator.resolve_cases(facts)
    if not cases and indicator.code != "I10":
        errors.append(
            ImportError(
                row_number,
                indicator.column(indicator.key_column).header,
                "no_object",
                "Не удалось определить объект (кадастровый номер или описание).",
            )
        )
        return None
    key = str(facts[indicator.key_column]["value"])[:200]
    title = str(facts[indicator.title_column]["value"])[:300]
    return ParsedRow(row_number, facts, author_mark, key, title, cases)


def _row_number(row):
    for cell in row:
        if cell["cell"]:
            return int("".join(char for char in cell["cell"] if char.isdigit()))
    return 0


@transaction.atomic
def _save(actor, name, content, file_format, table):
    indicator = table.indicator
    real = sum(
        1
        for row in table.rows
        for fact in row.facts.values()
        if fact["origin"] == Origin.AUTHOR_MARKED_REAL
    )
    synthetic = sum(
        1
        for row in table.rows
        for fact in row.facts.values()
        if fact["state"] == PRESENT and fact["origin"] in (Origin.SYNTHETIC, Origin.UNKNOWN)
    )
    sources = [note for note in table.notes if normalize_header(note).startswith("источник")]
    batch = ImportBatch.objects.create(
        file_name=name[:255],
        sha256=hashlib.sha256(content).hexdigest(),
        file_format=file_format,
        indicator=indicator.code,
        sheet=table.sheet[:100],
        uploaded_by=actor,
        rows_total=len(table.rows),
        real_cells=real,
        synthetic_cells=synthetic,
        sources_note="\n".join(sources),
        notes="\n".join(note for note in table.notes if note not in sources),
    )
    created = updated = 0
    touched_cases = {}
    for row in table.rows:
        is_demo = any(
            fact["state"] == PRESENT and fact["origin"] in (Origin.SYNTHETIC, Origin.UNKNOWN)
            for fact in row.facts.values()
        )
        record, was_created = Record.objects.update_or_create(
            indicator=indicator.code,
            source_key=row.key,
            defaults={
                "title": row.title,
                "batch": batch,
                "sheet": table.sheet[:100],
                "row_number": row.row_number,
                "facts": row.facts,
                "author_mark": row.author_mark[:60],
                "is_demonstration": is_demo,
            },
        )
        created += was_created
        updated += not was_created
        cases = [_upsert_case(spec, row, batch) for spec in row.cases]
        record.cases.set(cases)
        for case in cases:
            touched_cases[case.pk] = case
    for case in touched_cases.values():
        _refresh_case_origin(case)
    batch.rows_created, batch.rows_updated = created, updated
    batch.save(update_fields=["rows_created", "rows_updated"])
    return ImportResult(batch_id=batch.id, case_ids=tuple(touched_cases))


def _upsert_case(spec, row, batch):
    case, _ = Case.objects.get_or_create(
        reference=spec.reference[:100],
        defaults={"title": spec.title[:300], "cadastral_number": spec.cadastral_number},
    )
    changed = False
    for attribute in ("cadastral_number", "object_kind", "address", "area_sq_m"):
        value = getattr(spec, attribute)
        if value and not getattr(case, attribute):
            setattr(case, attribute, value)
            changed = True
    if spec.geometry and (not case.geometry or row.facts.get("coords")):
        case.geometry = spec.geometry
        changed = True
    if spec.address and case.title.startswith(("Земельный участок ", "Объект ")):
        case.title = spec.title[:300]
        changed = True
    if not case.region:
        case.region = region_for(case.cadastral_number, case.address)
        changed = bool(case.region) or changed
    if batch.sources_note and not case.source_reference:
        case.source_reference = batch.sources_note.split("\n")[0][:500]
        changed = True
    if changed:
        case.save()
    return case


def _refresh_case_origin(case):
    records = list(case.records.all())
    case.is_demonstration = any(record.is_demonstration for record in records) or not records
    key_real = any(
        fact.get("origin") == Origin.AUTHOR_MARKED_REAL
        for record in records
        for fact in record.facts.values()
    )
    case.origin = (
        Origin.AUTHOR_MARKED_REAL
        if key_real and not case.is_demonstration
        else (Origin.SYNTHETIC if case.is_demonstration else Origin.UNKNOWN)
    )
    case.save(update_fields=["is_demonstration", "origin", "updated_at"])
