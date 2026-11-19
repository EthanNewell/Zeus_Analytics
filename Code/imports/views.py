from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from cases.indicators import INDICATORS

from .models import ImportBatch
from .services import import_table


@permission_required(["cases.view_case", "cases.import_cases"], raise_exception=True)
@require_http_methods(["GET", "POST"])
def upload(request):
    errors = ()
    if request.method == "POST":
        result = import_table(actor=request.user, uploaded_file=request.FILES.get("file"))
        if not result.errors:
            return redirect("imports:batch", batch_id=result.batch_id)
        errors = result.errors
    return render(
        request,
        "imports/upload.html",
        {
            "errors": errors,
            "batches": ImportBatch.objects.select_related("uploaded_by")[:30],
            "indicators": INDICATORS.values(),
        },
        status=400 if errors else 200,
    )


@permission_required(["cases.view_case", "cases.import_cases"], raise_exception=True)
@require_GET
def batch(request, batch_id):
    item = get_object_or_404(ImportBatch.objects.select_related("uploaded_by"), pk=batch_id)
    return render(
        request,
        "imports/batch.html",
        {
            "batch": item,
            "indicator": INDICATORS.get(item.indicator),
            "records": item.records.prefetch_related("cases"),
        },
    )
