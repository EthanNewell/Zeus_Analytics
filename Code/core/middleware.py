import logging
import time
import uuid

from django.conf import settings
from django.utils.cache import patch_cache_control

logger = logging.getLogger("application.requests")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        started = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        patch_cache_control(response, private=True, no_store=True)
        match = getattr(request, "resolver_match", None)
        logger.info(
            "request_id=%s view=%s status=%s duration_ms=%.1f version=%s",
            request.request_id,
            match.view_name if match else "unresolved",
            response.status_code,
            (time.monotonic() - started) * 1000,
            settings.APP_VERSION,
        )
        return response
