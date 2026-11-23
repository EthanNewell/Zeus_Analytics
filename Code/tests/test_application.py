import csv
import io
import uuid
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.roles import ROLES
from cases.models import Case, Evidence, Origin, Review
from cases.services import add_review
from imports.contracts import ImportError, ImportResult

User = get_user_model()


class ApplicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_roles", verbosity=0)
        cls.user = User.objects.create_user("analyst", password="a-useful-test-password")
        cls.user.groups.add(Group.objects.get(name="Specialist"))
        cls.other = User.objects.create_user("outsider", password="another-test-password")
        cls.head = User.objects.create_user("head", password="a-head-test-password")
        cls.head.groups.add(Group.objects.get(name="Head"))
        cls.case = Case.objects.create(
            reference="TEST-01", title="Учебный участок", origin=Origin.SYNTHETIC
        )
        cls.evidence = Evidence.objects.create(
            case=cls.case,
            title="Документ",
            download_name="source.txt",
            file=SimpleUploadedFile("private.txt", b"private evidence"),
        )

    def test_guest_cannot_read_data_or_write(self):
        routes = [
            ("dashboard:case_list", [], "get"),
            ("dashboard:case_detail", [self.case.id], "get"),
            ("dashboard:case_export", [], "get"),
            ("dashboard:evidence_download", [self.evidence.id], "get"),
            ("dashboard:review_create", [self.case.id], "post"),
            ("imports:upload", [], "get"),
            ("analysis:run", [], "post"),
        ]
        for name, args, method in routes:
            with self.subTest(route=name):
                response = getattr(self.client, method)(reverse(name, args=args))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("accounts:login") + "?next="))

    def test_login_without_permissions_is_not_enough(self):
        self.client.force_login(self.other)
        for name in ["dashboard:case_list", "dashboard:case_export", "imports:upload"]:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_demo_account_12345_opens_the_main_page_with_full_rights(self):
        from django.core.management import call_command
        from django.test import override_settings

        with override_settings(ENABLE_SYNTHETIC_LOGIN=True):
            call_command("demo_users", stdout=StringIO())
        response = self.client.post(
            reverse("accounts:login"), {"username": "12345", "password": "12345"}
        )
        self.assertRedirects(response, reverse("dashboard:overview"))
        main = self.client.get(reverse("dashboard:overview"))
        self.assertContains(main, "Алексей М.")
        self.assertContains(main, "Руководитель")
        self.assertEqual(self.client.get(reverse("imports:upload")).status_code, 200)

    def test_login_uses_local_next(self):
        destination = reverse("dashboard:case_detail", args=[self.case.id])
        self.assertRedirects(
            self.client.post(
                reverse("accounts:login"),
                {
                    "username": "analyst",
                    "password": "a-useful-test-password",
                    "next": destination,
                },
            ),
            destination,
        )

    def test_external_next_is_rejected(self):
        self.assertRedirects(
            self.client.post(
                reverse("accounts:login"),
                {
                    "username": "analyst",
                    "password": "a-useful-test-password",
                    "next": "https://evil.example/",
                },
            ),
            reverse("dashboard:overview"),
        )

    def test_wrong_password_and_inactive_user_are_rejected(self):
        for active, password in [(True, "wrong"), (False, "a-useful-test-password")]:
            self.user.is_active = active
            self.user.save(update_fields=["is_active"])
            response = self.client.post(
                reverse("accounts:login"), {"username": "analyst", "password": password}
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_removes_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.post(reverse("accounts:logout")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_on_login_logout_and_review(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("accounts:login")).status_code, 403)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("accounts:logout")).status_code, 403)
        self.assertEqual(
            client.post(
                reverse("dashboard:review_create", args=[self.case.id]),
                {
                    "outcome": "needs_information",
                    "comment": "Проверить документ",
                },
            ).status_code,
            403,
        )
        self.assertFalse(Review.objects.exists())

    def test_specialist_cannot_manage_users(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("admin:accounts_user_changelist")).status_code, 302
        )
        self.assertFalse(self.user.has_perm("accounts.change_user"))

    def test_attachment_requires_permissions_and_is_downloaded(self):
        self.client.force_login(self.user)
        url = reverse("dashboard:evidence_download", args=[self.evidence.id])
        response = self.client.get(url)
        self.assertEqual(b"".join(response.streaming_content), b"private evidence")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        # Consuming streaming_content already closed the response with the test client's
        # signal guard; a second close() would fire request_finished and drop the
        # MySQL connection in the middle of the test transaction.
        self.user.groups.clear()
        self.user.user_permissions.add(
            Permission.objects.get(codename="view_case", content_type__app_label="cases")
        )
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_direct_media_url_is_not_exposed(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get("/private-media/" + self.evidence.file.name).status_code, 404
        )

    def test_private_responses_have_request_id_and_no_store(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:case_list"))
        self.assertIn("no-store", response["Cache-Control"])
        uuid.UUID(response["X-Request-ID"])

    def test_specialist_cannot_import_or_run_analysis(self):
        self.client.force_login(self.user)
        before = Case.objects.count()
        self.assertEqual(self.client.post(reverse("imports:upload")).status_code, 403)
        self.assertEqual(self.client.post(reverse("analysis:run")).status_code, 403)
        self.assertEqual(Case.objects.count(), before)

    def test_empty_upload_and_empty_analysis_do_not_fake_success(self):
        self.client.force_login(self.head)
        before = Case.objects.count()
        response = self.client.post(reverse("imports:upload"))
        self.assertContains(response, "Файл не загружен", status_code=400)
        response = self.client.post(reverse("analysis:run"), follow=True)
        self.assertContains(response, "Нет загруженных записей")
        self.assertEqual(Case.objects.count(), before)

    def test_health_is_public_and_readiness_does_not_leak_errors(self):
        self.assertEqual(self.client.get(reverse("core:live")).json(), {"status": "ok"})
        self.assertEqual(self.client.get(reverse("core:ready")).status_code, 200)
        with patch(
            "core.views.connection.cursor", side_effect=OperationalError("secret connection detail")
        ):
            response = self.client.get(reverse("core:ready"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn(b"secret", response.content)

    def test_readiness_detects_missing_migrations(self):
        with patch("core.views.MigrationExecutor") as executor:
            executor.return_value.migration_plan.return_value = [object()]
            self.assertEqual(self.client.get(reverse("core:ready")).status_code, 503)

    @override_settings(DEBUG=False)
    def test_error_page_has_reference_without_traceback(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("dashboard:case_list"))
        self.assertContains(response, "Код обращения", status_code=403)
        self.assertNotIn(b"Traceback", response.content)

    def test_login_list_card_review_history_export(self):
        self.assertTrue(self.client.login(username="analyst", password="a-useful-test-password"))
        self.assertContains(self.client.get(reverse("dashboard:case_list")), self.case.title)
        detail = reverse("dashboard:case_detail", args=[self.case.id])
        self.assertContains(self.client.get(detail), "Синтетическое")
        for outcome in ["needs_information", "not_confirmed"]:
            response = self.client.post(
                reverse("dashboard:review_create", args=[self.case.id]),
                {
                    "outcome": outcome,
                    "comment": "Основание: учебный документ",
                    "author": self.other.pk,
                },
            )
            self.assertRedirects(response, detail)
        reviews = Review.objects.filter(case=self.case)
        self.assertEqual(reviews.count(), 2)
        self.assertEqual({r.author_id for r in reviews}, {self.user.pk})
        self.case.refresh_from_db()
        self.assertEqual(self.case.title, "Учебный участок")
        self.assertEqual(self.client.get(reverse("dashboard:case_export")).status_code, 403)
        self.client.force_login(self.head)
        response = self.client.get(reverse("dashboard:case_export"))
        row = list(
            csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
        )[0]
        self.assertEqual(
            (
                row["Демонстрационные данные"],
                row["Итог анализа"],
                row["Результат проверки сотрудника"],
            ),
            ("да", "Анализ не запускался", "Не подтверждено"),
        )

    def test_invalid_review_does_not_write(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("dashboard:review_create", args=[self.case.id]),
            {"outcome": "made_up", "comment": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Review.objects.exists())

    def test_review_service_checks_permission(self):
        with self.assertRaises(PermissionDenied):
            add_review(
                actor=self.other, case=self.case, outcome="needs_information", comment="test"
            )

    def test_export_uses_filter_and_escapes_spreadsheet_formulas(self):
        self.client.force_login(self.head)
        self.case.title = '  =HYPERLINK("https://example.org")'
        self.case.save(update_fields=["title"])
        Case.objects.create(reference="OTHER", title="Другой случай")
        response = self.client.get(reverse("dashboard:case_export"), {"q": "TEST-01"})
        rows = list(
            csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
        )
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["Объект"].startswith("'"))

    def test_bootstrap_is_idempotent_and_roles_are_nested(self):
        groups = {role.group: role for role in ROLES}
        before = {
            name: set(Group.objects.get(name=name).permissions.values_list("codename", flat=True))
            for name in groups
        }
        call_command("bootstrap_roles", verbosity=0)
        for name, role in groups.items():
            current = set(
                Group.objects.get(name=name).permissions.values_list("codename", flat=True)
            )
            self.assertEqual(current, before[name])
            self.assertEqual(current, set(role.permissions))
        self.assertLess(before["Specialist"], before["Controller"])
        self.assertLess(before["Controller"], before["Head"])
        self.assertNotIn("import_cases", before["Specialist"])
        self.assertNotIn("export_cases", before["Controller"])

    def test_import_contract_rejects_ambiguous_results(self):
        with self.assertRaises(ValueError):
            ImportResult(batch_id=uuid.uuid4(), errors=(ImportError(2, "date", "invalid", "Дата"),))
