from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = "Пользователи и доступ"

    def ready(self):
        from .demo import after_migrate

        post_migrate.connect(after_migrate, dispatch_uid="accounts.demo_guest")
