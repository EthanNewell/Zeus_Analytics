import logging

from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@login_not_required
@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@login_not_required
@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except DatabaseError:
        logger.warning("Readiness database check failed request_id=%s", request.request_id)
        return JsonResponse({"status": "unavailable"}, status=503)
    if pending:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def error_page(request, status):
    return render(request, "errors/error.html", {"status_code": status}, status=status)


def bad_request(request, exception):
    return error_page(request, 400)


def permission_denied(request, exception):
    return error_page(request, 403)


def not_found(request, exception):
    return error_page(request, 404)


def server_error(request):
    return error_page(request, 500)
