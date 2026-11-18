from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .services import AnalysisNotConfigured, run_analysis


@permission_required(["cases.view_case", "cases.run_analysis"], raise_exception=True)
@require_POST
def run(request):
    try:
        result = run_analysis(actor=request.user, case_ids=request.POST.getlist("case_ids"))
    except AnalysisNotConfigured as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Анализ выполнен за {result.duration_ms} мс: {result.records_count} записей, "
            f"{result.triggered_count} сработавших индикаторов, {result.cases_count} объектов.",
        )
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}):
        target = ""
    return redirect(target or "dashboard:overview")
