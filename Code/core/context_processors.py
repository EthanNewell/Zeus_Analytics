from django.conf import settings

from accounts.roles import role_label


def application(request):
    user = getattr(request, "user", None)
    signed_in = user is not None and user.is_authenticated
    if signed_in:
        from analysis.models import AnalysisRun

        last_run = AnalysisRun.objects.only("started_at").first()
    else:
        last_run = None
    return {
        "last_run": last_run,
        "app_version": settings.APP_VERSION,
        "user_role": role_label(user) if user is not None and user.is_authenticated else "",
    }
