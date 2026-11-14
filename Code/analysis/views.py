from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .services import AnalysisNotConfigured, run_analysis


@permission_required(["cases.view_case", "cases.run_analysis"], raise_exception=True)
@require_POST
def run(request):
    try:
        run_analysis(actor=request.user, case_ids=request.POST.getlist("case_ids"))
    except AnalysisNotConfigured as error:
        return render(
            request, "dashboard/module.html", {"title": "Анализ", "detail": str(error)}, status=501
        )
    raise RuntimeError("Wire the AnalysisRun redirect when implementing the analysis adapter")
