from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .services import ImportNotConfigured, import_csv


@permission_required(["cases.view_case", "cases.import_cases"], raise_exception=True)
@require_http_methods(["GET", "POST"])
def upload(request):
    if request.method == "POST":
        try:
            import_csv(actor=request.user, uploaded_file=request.FILES.get("file"))
        except ImportNotConfigured as error:
            return render(
                request,
                "dashboard/module.html",
                {"title": "Импорт данных", "detail": str(error)},
                status=501,
            )
    return render(
        request,
        "dashboard/module.html",
        {
            "title": "Импорт данных",
            "detail": "Импорт пока недоступен. До начала загрузки необходимо согласовать формат и происхождение исходных данных.",
        },
    )
