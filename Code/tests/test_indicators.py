"""Control set for the indicator rules, the import and the full user path."""

import io

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from analysis.contracts import Priority, RuleStatus
from analysis.models import RuleOutcome
from analysis.rules import RULES, expected_status
from analysis.services import run_analysis, summarize
from cases.facts import cadastral_numbers
from cases.indicators import INDICATORS
from cases.models import Attention, Case, Origin, Record
from imports.models import ImportBatch
from imports.services import import_table

User = get_user_model()

L_SHAPE = "46.553200 41.041800; 46.553200 41.042584; 46.553272 41.042584; 46.553272 41.041957; 46.553559 41.041957; 46.553559 41.041800"
RECTANGLE = "47.267100 39.870200; 47.267147 39.870524; 47.267498 39.870414; 47.267451 39.870090"


def facts(**values):
    """Build rule input: None → «нет данных», "—" → event absent, else present."""
    result = {}
    for key, value in values.items():
        if value is None:
            result[key] = {
                "value": None,
                "state": "missing",
                "origin": "",
                "cell": "",
                "label": key,
            }
        elif value == "—":
            result[key] = {
                "value": None,
                "state": "absent",
                "origin": "synthetic",
                "cell": "",
                "label": key,
            }
        else:
            result[key] = {
                "value": value,
                "state": "present",
                "origin": "synthetic",
                "cell": "",
                "label": key,
            }
    return result


def evaluate(code, **values):
    return RULES[code].evaluate(facts(**values))


class RuleTests(TestCase):
    def assertStatus(self, result, status, priority=None):
        self.assertEqual(result.status, status, result.explanation)
        if priority:
            self.assertEqual(result.priority, priority)
        self.assertTrue(result.explanation.strip())
        if status == RuleStatus.INSUFFICIENT_DATA:
            self.assertTrue(result.missing)

    def test_i1_purchase_window(self):
        self.assertStatus(
            evaluate("I1", right_date="2025-05-22", category_change_date="2026-02-17"),
            RuleStatus.TRIGGERED,
            Priority.NORMAL,
        )
        self.assertStatus(
            evaluate("I1", right_date="2024-10-03", category_change_date="2026-03-18"),
            RuleStatus.NOT_TRIGGERED,
        )
        self.assertStatus(
            evaluate("I1", right_date="2026-03-01", category_change_date="2026-02-17"),
            RuleStatus.NOT_TRIGGERED,
        )
        self.assertStatus(
            evaluate("I1", right_date=None, category_change_date="2026-02-17"),
            RuleStatus.INSUFFICIENT_DATA,
        )

    def test_i1_window_border_is_inclusive(self):
        self.assertStatus(
            evaluate("I1", right_date="2025-02-28", category_change_date="2026-02-28"),
            RuleStatus.TRIGGERED,
        )
        self.assertStatus(
            evaluate("I1", right_date="2025-02-28", category_change_date="2026-03-01"),
            RuleStatus.NOT_TRIGGERED,
        )

    def test_i2_owner_share(self):
        self.assertStatus(evaluate("I2", zone_area=4.2, owner_area=4.2), RuleStatus.TRIGGERED)
        self.assertStatus(evaluate("I2", zone_area=12.5, owner_area=10.0), RuleStatus.TRIGGERED)
        self.assertStatus(evaluate("I2", zone_area=38.4, owner_area=4.6), RuleStatus.NOT_TRIGGERED)
        self.assertStatus(
            evaluate("I2", zone_area=None, owner_area=None), RuleStatus.INSUFFICIENT_DATA
        )

    def test_i3_is_context_and_needs_sale_after_change(self):
        base = dict(
            ks_before=151088,
            ks_after=6384000,
            category_change_date="2026-03-18",
            ks_after_start="2026-03-18",
        )
        self.assertStatus(
            evaluate("I3", resale_date="2026-09-10", **base), RuleStatus.TRIGGERED, Priority.LOW
        )
        self.assertStatus(evaluate("I3", resale_date="—", **base), RuleStatus.NOT_TRIGGERED)
        self.assertStatus(evaluate("I3", resale_date=None, **base), RuleStatus.INSUFFICIENT_DATA)
        revaluation = dict(base, ks_after_start="2026-01-01")
        self.assertStatus(
            evaluate("I3", resale_date="2026-06-09", **revaluation), RuleStatus.NOT_TRIGGERED
        )

    def test_i4_single_participant_or_bypass(self):
        self.assertStatus(
            evaluate("I4", participants=1, start_price=520000, final_price=520000),
            RuleStatus.TRIGGERED,
        )
        self.assertStatus(
            evaluate(
                "I4", participants="—", bypass="Второе заявление проигнорировано", final_price=18450
            ),
            RuleStatus.TRIGGERED,
        )
        self.assertStatus(
            evaluate("I4", participants=5, bypass="—", start_price=640000, final_price=1488000),
            RuleStatus.NOT_TRIGGERED,
        )
        self.assertStatus(
            evaluate("I4", participants=None, bypass=None), RuleStatus.INSUFFICIENT_DATA
        )

    def test_i6_link_must_be_documented(self):
        dates = dict(
            purchase_date="2025-05-22",
            procedure_start="2025-08-05",
            official="Ветров А.Н., ИНН 610214942629",
        )
        self.assertStatus(
            evaluate("I6", inn_match="Да — ИНН совпал", surname_match="Да", **dates),
            RuleStatus.TRIGGERED,
            Priority.HIGH,
        )
        surname = evaluate(
            "I6", inn_match="Нет — общих организаций нет", surname_match="Да — Кравченко", **dates
        )
        self.assertStatus(surname, RuleStatus.INSUFFICIENT_DATA)
        self.assertIn("фамилия", surname.explanation)
        self.assertStatus(
            evaluate("I6", inn_match="Нет", surname_match="Нет", **dates), RuleStatus.NOT_TRIGGERED
        )
        late = dict(dates, purchase_date="2026-02-04", procedure_start="2025-08-18")
        self.assertStatus(
            evaluate("I6", inn_match="Да", surname_match="Да", **late), RuleStatus.NOT_TRIGGERED
        )
        self.assertStatus(
            evaluate("I6", purchase_date="2026-02-12", procedure_start=None),
            RuleStatus.INSUFFICIENT_DATA,
        )

    def test_i8_fill_is_computed_from_coordinates(self):
        anomaly = evaluate("I8", coords=L_SHAPE, area=864)
        self.assertStatus(anomaly, RuleStatus.TRIGGERED)
        fill = dict(anomaly.metrics)["Коэффициент заполнения"]
        self.assertEqual(fill, "0,361")
        self.assertStatus(evaluate("I8", coords=RECTANGLE, area=1000), RuleStatus.NOT_TRIGGERED)
        self.assertStatus(evaluate("I8", coords=None), RuleStatus.INSUFFICIENT_DATA)

    def test_i10_repeated_official(self):
        self.assertStatus(
            evaluate("I10", person="Ветров А.Н.", repeats=5), RuleStatus.TRIGGERED, Priority.HIGH
        )
        self.assertStatus(
            evaluate("I10", person="Широков П.А.", repeats=1), RuleStatus.NOT_TRIGGERED
        )
        self.assertStatus(
            evaluate("I10", person="Иванов", repeats=None), RuleStatus.INSUFFICIENT_DATA
        )

    def test_author_marks_map_to_statuses(self):
        self.assertEqual(expected_status("Да"), "triggered")
        self.assertEqual(expected_status("1 — аномалия"), "triggered")
        self.assertEqual(expected_status("0 — норма"), "not_triggered")
        self.assertEqual(expected_status("Требует проверки"), "insufficient_data")
        self.assertEqual(expected_status(""), "")

    def test_every_indicator_has_one_rule(self):
        self.assertEqual(set(RULES), set(INDICATORS))


class Outcome:
    def __init__(self, code, status, priority="normal"):
        self.rule_code, self.status, self.priority = code, status, priority


class SummaryTests(TestCase):
    def test_case_attention(self):
        cases = [
            ([Outcome("I3", "triggered", "low")], Attention.LOW),
            ([Outcome("I1", "triggered")], Attention.NORMAL),
            ([Outcome("I1", "triggered"), Outcome("I2", "triggered")], Attention.HIGH),
            ([Outcome("I6", "triggered", "high")], Attention.HIGH),
            ([Outcome("I3", "triggered", "low"), Outcome("I1", "not_triggered")], Attention.LOW),
            ([Outcome("I8", "insufficient_data", "low")], Attention.INSUFFICIENT),
            ([Outcome("I8", "not_triggered", "low")], Attention.NONE),
        ]
        for outcomes, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(summarize(outcomes)[0], expected)

    def test_cadastral_numbers_expand_shorthand_and_ranges(self):
        self.assertEqual(
            cadastral_numbers(
                "правка — 61:02:0120102:1543, :1544; участок 61:01:0600005:3352 – :3354"
            ),
            [
                "61:01:0600005:3352",
                "61:01:0600005:3353",
                "61:01:0600005:3354",
                "61:02:0120102:1543",
                "61:02:0120102:1544",
            ],
        )


def i8_workbook(rows, notes=()):
    """An И8 table the way the research team prepares it: yellow = real, formulas = calculated."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Аномалия границ"
    sheet.append([column.header for column in INDICATORS["I8"].columns])
    for index, (number, coords, area) in enumerate(rows, start=2):
        sheet.append(
            [
                index - 1,
                number,
                "форма",
                coords,
                area,
                area,
                f"=E{index}/F{index}",
                f'=IF(G{index}>=0.85,"0 — норма","1 — аномалия")',
            ]
        )
    sheet["B2"].fill = PatternFill("solid", fgColor="FFFF00")
    for offset, note in enumerate(notes):
        sheet.cell(row=len(rows) + 3 + offset, column=1, value=note)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def i1_csv(rows):
    headers = [column.header for column in INDICATORS["I1"].columns]
    lines = [";".join(headers)]
    for number, bought, changed in rows:
        values = {
            "number": "1",
            "object_kind": "Земельный участок",
            "cadastral": number,
            "right_date": bought,
            "category_change_date": changed,
            "category_before": "Земли с/х назначения",
            "category_after": "Земли населённых пунктов",
            "holder": "ООО «Тест»",
            "mark": "Да",
        }
        lines.append(
            ";".join(values.get(column.key, "нет данных") for column in INDICATORS["I1"].columns)
        )
    return "\n".join(lines).encode("utf-8")


class ImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_roles", verbosity=0)
        cls.controller = User.objects.create_user(
            "controller", password="a-controller-test-password"
        )
        cls.controller.groups.add(Group.objects.get(name="Controller"))
        cls.specialist = User.objects.create_user(
            "specialist", password="a-specialist-test-password"
        )
        cls.specialist.groups.add(Group.objects.get(name="Specialist"))

    def upload(self, name, content, actor=None):
        return import_table(
            actor=actor or self.controller, uploaded_file=SimpleUploadedFile(name, content)
        )

    def test_xlsx_keeps_provenance_geometry_and_notes(self):
        result = self.upload(
            "И8.xlsx",
            i8_workbook(
                [("31:19:0504002:36", RECTANGLE, 1000), ("61:39:0600012:744", L_SHAPE, 864)],
                notes=["Источники координат: НСПД, выписка ЕГРН.", "Порог 0,85 — допущение."],
            ),
        )
        self.assertFalse(result.errors)
        record = Record.objects.get(source_key="31:19:0504002:36")
        self.assertEqual(record.facts["cadastral"]["origin"], Origin.AUTHOR_MARKED_REAL)
        self.assertEqual(record.facts["cadastral"]["cell"], "B2")
        self.assertEqual(record.facts["coords"]["origin"], Origin.SYNTHETIC)
        self.assertEqual(record.facts["fill"]["origin"], Origin.CALCULATED)
        case = Case.objects.get(reference="61:39:0600012:744")
        self.assertEqual(len(case.geometry), 6)
        self.assertEqual(case.region, "Ростовская обл.")
        batch = ImportBatch.objects.get()
        self.assertIn("НСПД", batch.sources_note)
        self.assertIn("Порог", batch.notes)
        self.assertEqual(batch.real_cells, 1)

    def test_bad_row_rejects_whole_file(self):
        result = self.upload(
            "И1.csv",
            i1_csv(
                [
                    ("61:02:0600010:2843", "22.05.2025", "17.02.2026"),
                    ("61:25:0600301:4127", "вчера", "18.03.2026"),
                ]
            ),
        )
        self.assertEqual(
            [(error.row, error.code) for error in result.errors], [(3, "invalid_value")]
        )
        self.assertFalse(Record.objects.exists())
        self.assertFalse(Case.objects.exists())
        self.assertFalse(ImportBatch.objects.exists())

    def test_reimport_updates_instead_of_duplicating(self):
        content = i1_csv([("61:02:0600010:2843", "22.05.2025", "17.02.2026")])
        self.upload("И1.csv", content)
        self.upload("И1.csv", content)
        self.assertEqual(Record.objects.count(), 1)
        self.assertEqual(Case.objects.count(), 1)
        self.assertEqual(ImportBatch.objects.first().rows_updated, 1)
        self.assertEqual(Record.objects.get().facts["right_date"]["origin"], Origin.UNKNOWN)

    def test_duplicate_keys_and_unknown_tables_are_rejected(self):
        duplicate = i1_csv([("61:02:0600010:2843", "22.05.2025", "17.02.2026")] * 2)
        self.assertEqual(self.upload("И1.csv", duplicate).errors[0].code, "duplicate")
        self.assertEqual(self.upload("x.csv", b"a;b;c\n1;2;3").errors[0].code, "unknown_table")
        self.assertEqual(self.upload("x.pdf", b"%PDF").errors[0].code, "format")
        self.assertEqual(self.upload("x.xlsx", b"not a zip").errors[0].code, "unreadable")
        self.assertFalse(Record.objects.exists())

    def test_import_requires_permission(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self.upload(
                "И1.csv",
                i1_csv([("61:02:0600010:2843", "22.05.2025", "17.02.2026")]),
                actor=self.specialist,
            )

    def test_analysis_stores_outcomes_and_case_attention(self):
        self.upload(
            "И1.csv",
            i1_csv(
                [
                    ("61:02:0600010:2843", "22.05.2025", "17.02.2026"),
                    ("61:25:0600301:4127", "03.10.2024", "18.03.2026"),
                ]
            ),
        )
        run = run_analysis(actor=self.controller)
        self.assertEqual((run.records_count, run.triggered_count), (2, 1))
        self.assertEqual((run.compared_count, run.agreed_count), (2, 1))
        self.assertEqual(
            Case.objects.get(reference="61:02:0600010:2843").attention, Attention.NORMAL
        )
        self.assertEqual(Case.objects.get(reference="61:25:0600301:4127").attention, Attention.NONE)
        first = RuleOutcome.objects.get(record__source_key="61:02:0600010:2843")
        self.assertEqual(first.used_fields, ["right_date", "category_change_date"])
        run_analysis(actor=self.controller)
        self.assertEqual(RuleOutcome.objects.count(), 4, "each run keeps its own immutable results")


class UserPathTests(TestCase):
    """Login → upload → analysis → registry → card → review → export, through the views."""

    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_roles", verbosity=0)
        cls.head = User.objects.create_user("head", password="a-head-test-password")
        cls.head.groups.add(Group.objects.get(name="Head"))

    def test_full_path(self):
        self.client.force_login(self.head)
        response = self.client.post(
            reverse("imports:upload"),
            {
                "file": SimpleUploadedFile(
                    "И8.xlsx", i8_workbook([("61:39:0600012:744", L_SHAPE, 864)])
                )
            },
        )
        batch = ImportBatch.objects.get()
        self.assertRedirects(response, reverse("imports:batch", args=[batch.id]))
        self.assertContains(self.client.get(response.url), "61:39:0600012:744")
        response = self.client.post(
            reverse("analysis:run"), {"next": reverse("dashboard:case_list")}, follow=True
        )
        self.assertContains(response, "Анализ выполнен")
        self.assertContains(response, "Требует проверки")
        case = Case.objects.get(reference="61:39:0600012:744")
        detail = self.client.get(reverse("dashboard:case_detail", args=[case.id]))
        self.assertContains(detail, "описанного прямоугольника")
        self.assertContains(detail, "outline-plate")
        self.client.post(
            reverse("dashboard:review_create", args=[case.id]),
            {"outcome": "confirmed", "comment": "Сверено с выпиской ЕГРН"},
        )
        export = self.client.get(reverse("dashboard:case_export")).content.decode("utf-8-sig")
        self.assertIn("Основания для дальнейшей проверки подтверждены", export)
        self.assertIn("И8: Контур заполняет", export)
        for name in ["overview", "map", "officials", "methodology"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"dashboard:{name}")).status_code, 200)
        filtered = self.client.get(
            reverse("dashboard:case_list"), {"attention": "normal", "indicator": "I8"}
        )
        self.assertContains(filtered, "61:39:0600012:744")
        self.assertNotContains(
            self.client.get(reverse("dashboard:case_list"), {"attention": "high"}),
            "61:39:0600012:744",
        )
