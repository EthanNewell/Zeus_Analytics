from django.conf import settings

from accounts.roles import role_label


def application(request):
    user = getattr(request, "user", None)
    signed_in = user is not None and user.is_authenticated
    if signed_in:
        from analysis.models import AnalysisRun
        from cases.selectors import queue_counts, recent_events

        last_run = AnalysisRun.objects.only("started_at").first()
        counts = queue_counts()
        events = recent_events(6)
    else:
        last_run, counts, events = None, {}, []
    return {
        "queue": counts,
        "queue_open": counts.get("high", 0) + counts.get("medium", 0) + counts.get("low", 0),
        "notifications": events,
        "last_run": last_run,
        "app_version": settings.APP_VERSION,
        "user_role": role_label(user) if user is not None and user.is_authenticated else "",
        "document_form": _document_form(user) if signed_in else None,
    }


def _document_form(user):
    """The upload window is drawn on every page for those who may add documents."""
    if not user.has_perms(["cases.view_case", "cases.add_evidence"]):
        return None
    from dashboard.forms import DocumentForm

    return DocumentForm()
