import csv

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from cases.models import Case, Evidence
from cases.selectors import case_list
from cases.services import add_review

from .forms import ReviewForm


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def cases(request):
    query = request.GET.get("q", "").strip()[:200]
    objects = case_list(query)
    page = Paginator(objects, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/case_list.html", {"page_obj": page, "query": query})


def detail_context(request, case, form=None):
    return {
        "case": case,
        "review_form": form if form is not None else ReviewForm(),
        "reviews": case.reviews.select_related("author")
        if request.user.has_perm("cases.view_review")
        else [],
        "evidence": case.evidence.all() if request.user.has_perm("cases.view_evidence") else [],
    }


@permission_required("cases.view_case", raise_exception=True)
@require_GET
def case_detail(request, case_id):
    case = get_object_or_404(Case, pk=case_id)
    return render(request, "dashboard/case_detail.html", detail_context(request, case))


@permission_required(["cases.view_case", "cases.add_review"], raise_exception=True)
@require_POST
def review_create(request, case_id):
    case = get_object_or_404(Case, pk=case_id)
    form = ReviewForm(request.POST)
    if form.is_valid():
        add_review(actor=request.user, case=case, **form.cleaned_data)
        messages.success(request, "Результат проверки сохранён в истории.")
        return redirect("dashboard:case_detail", case_id=case.id)
    return render(
        request, "dashboard/case_detail.html", detail_context(request, case, form), status=400
    )


def csv_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


@permission_required(["cases.view_case", "cases.export_cases"], raise_exception=True)
@require_GET
def case_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cases.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        ["reference", "title", "cadastral_number", "origin", "is_demonstration", "analysis_status"]
    )
    query = request.GET.get("q", "").strip()[:200]
    for case in case_list(query).iterator(chunk_size=200):
        writer.writerow(
            [
                csv_cell(value)
                for value in (
                    case.reference,
                    case.title,
                    case.cadastral_number,
                    case.origin,
                    case.is_demonstration,
                    "not_run",
                )
            ]
        )
    return response


@permission_required(["cases.view_case", "cases.view_evidence"], raise_exception=True)
@require_GET
def evidence_download(request, evidence_id):
    evidence = get_object_or_404(Evidence, pk=evidence_id)
    if not evidence.file:
        raise Http404
    try:
        file = evidence.file.open("rb")
    except FileNotFoundError as error:
        raise Http404 from error
    return FileResponse(
        file,
        as_attachment=True,
        filename=evidence.download_name,
        content_type="application/octet-stream",
    )
