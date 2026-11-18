from django.conf import settings

from accounts.roles import role_label


def application(request):
    user = getattr(request, "user", None)
    return {
        "app_version": settings.APP_VERSION,
        "user_role": role_label(user) if user is not None and user.is_authenticated else "",
    }
