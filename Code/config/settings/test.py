from .base import *  # noqa: F403

SECRET_KEY = "test-only-key-never-use-on-a-server"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
