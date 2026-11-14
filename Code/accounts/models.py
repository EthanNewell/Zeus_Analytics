from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Meta(AbstractUser.Meta):
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
