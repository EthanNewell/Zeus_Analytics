import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
required = [
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_HOST",
]
for name in required:
    if not os.environ.get(name, "").strip():
        raise ImproperlyConfigured(f"{name} is required on staging")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith(("local-", "test-", "change-")):  # noqa: F405
    raise ImproperlyConfigured("Use a random DJANGO_SECRET_KEY of at least 50 characters")
if DB_ENGINE != "mysql":  # noqa: F405
    raise ImproperlyConfigured("Staging requires MySQL")
if "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Wildcard ALLOWED_HOSTS is forbidden on staging")
if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("Staging CSRF origins must use HTTPS")

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^health/live/$", r"^health/ready/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# This staging host does not control sibling/subdomains and is not preloaded.
# Keep other deployment warnings blocking; these two choices are intentional.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
