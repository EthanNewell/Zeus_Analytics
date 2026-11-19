import os
import subprocess
import sys

from django.test import SimpleTestCase


class StagingSettingsTests(SimpleTestCase):
    def load_settings(self, **overrides):
        environment = (
            os.environ
            | {
                "DJANGO_SECRET_KEY": "a-valid-staging-secret-" + "x" * 64,
                "DJANGO_ALLOWED_HOSTS": "staging.example.org",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.example.org",
                "DB_ENGINE": "mysql",
                "MYSQL_DATABASE": "transparency",
                "MYSQL_USER": "transparency",
                "MYSQL_PASSWORD": "test-setting-only",
                "MYSQL_HOST": "db",
            }
            | overrides
        )
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from config.settings import staging; assert staging.DEBUG is False",
            ],
            env=environment,
            capture_output=True,
            text=True,
        )

    def test_production_settings_accept_explicit_configuration(self):
        self.assertEqual(self.load_settings().returncode, 0)

    def test_missing_secret_fails_startup(self):
        result = self.load_settings(DJANGO_SECRET_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY is required", result.stderr)

    def test_wildcard_host_is_rejected(self):
        self.assertNotEqual(self.load_settings(DJANGO_ALLOWED_HOSTS="*").returncode, 0)

    def test_sqlite_is_not_allowed_on_staging(self):
        self.assertNotEqual(self.load_settings(DB_ENGINE="sqlite").returncode, 0)

    def test_insecure_origin_is_rejected(self):
        self.assertNotEqual(
            self.load_settings(DJANGO_CSRF_TRUSTED_ORIGINS="http://staging.example.org").returncode,
            0,
        )
