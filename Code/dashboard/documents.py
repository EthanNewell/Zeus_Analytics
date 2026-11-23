import uuid
from pathlib import Path

from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from cases.models import Case, Evidence
from cases.services import EVIDENCE_MAX_BYTES

DOCUMENT_TYPES = {".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@permission_required(["cases.view_case", "cases.add_evidence"], raise_exception=True)
@require_POST
def upload_documents(request):
    files = request.FILES.getlist("file")
    if not 1 <= len(files) <= 10 or sum(item.size for item in files) > 20 * 1024 * 1024:
        return JsonResponse(
            {"error": "Выберите от 1 до 10 файлов общим размером до 20 МБ."}, status=400
        )
    metadata = {
        key: request.POST.getlist(key)
        for key in ("document_type", "source_reference", "description")
    }
    if any(values and len(values) != len(files) for values in metadata.values()):
        return JsonResponse({"error": "Проверьте сведения для каждого файла."}, status=400)
    # from a card the documents go to its object; from the registry they stay in the common list
    case = None
    if request.POST.get("case"):
        try:
            case = get_object_or_404(Case, pk=uuid.UUID(request.POST["case"]))
        except ValueError:
            return JsonResponse({"error": "Объект не найден."}, status=400)
    documents = []
    for index, item in enumerate(files):
        if (
            Path(item.name).suffix.lower() not in DOCUMENT_TYPES
            or not 0 < item.size <= EVIDENCE_MAX_BYTES
        ):
            return JsonResponse(
                {"error": f"{item.name}: нужен файл допустимого формата размером до 5 МБ."},
                status=400,
            )
        fields = {key: values[index].strip() for key, values in metadata.items() if values}
        if any(
            len(value) > Evidence._meta.get_field(key).max_length for key, value in fields.items()
        ):
            return JsonResponse(
                {"error": "Сократите описание, источник или тип документа."}, status=400
            )
        name = Path(item.name).name[:200]
        documents.append(
            Evidence(
                case=case,
                file=item,
                title=name,
                download_name=name,
                added_by=request.user,
                **fields,
            )
        )

    # File storage is outside the database transaction. Remove files if a batch rolls back.
    try:
        with transaction.atomic():
            for document in documents:
                document.save(force_insert=True)
    except Exception:
        for document in documents:
            if document.file._committed:
                document.file.delete(save=False)
        raise
    return JsonResponse({"count": len(documents)}, status=201)
