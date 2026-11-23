from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cases.models import Evidence


@override_settings(ENABLE_SYNTHETIC_LOGIN=True)
class RegistryDocumentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_users", stdout=StringIO())

    def test_demo_session_can_upload_and_retrieve_files(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "12345", "password": "12345"}
        )
        self.assertRedirects(response, reverse("dashboard:overview"))
        self.assertContains(self.client.get(reverse("dashboard:case_list")), "Загрузить документ")
        response = self.client.post(
            reverse("dashboard:upload_documents"),
            {
                "file": [
                    SimpleUploadedFile("first.pdf", b"%PDF-1.7"),
                    SimpleUploadedFile("second.tiff", b"II"),
                ],
                "document_type": ["Выписка из ЕГРН", ""],
                "source_reference": ["Росреестр", ""],
                "description": ["Для проверки", ""],
            },
        )
        self.assertEqual(response.status_code, 201)
        first = Evidence.objects.get(title="first.pdf")
        self.assertEqual(first.description, "Для проверки")
        self.assertIsNone(first.case_id)
        self.assertEqual(first.added_by.username, "12345")
        self.assertContains(self.client.get(reverse("dashboard:case_list")), "second.tiff")
        self.assertContains(self.client.get(reverse("dashboard:search_index")), "first.pdf")
        response = self.client.get(reverse("dashboard:evidence_download", args=[first.pk]))
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.7")

    def test_invalid_batch_saves_nothing(self):
        self.client.force_login(get_user_model().objects.get(username="12345"))
        response = self.client.post(
            reverse("dashboard:upload_documents"),
            {
                "file": [
                    SimpleUploadedFile("first.pdf", b"data"),
                    SimpleUploadedFile("invalid.exe", b"x"),
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Evidence.objects.exists())

    def test_upload_requires_permissions_and_csrf(self):
        url = reverse("dashboard:upload_documents")
        outsider = get_user_model().objects.create_user(username="reader")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        client.force_login(get_user_model().objects.get(username="12345"))
        self.assertEqual(client.post(url).status_code, 403)
