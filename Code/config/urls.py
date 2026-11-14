from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path(
        "", RedirectView.as_view(pattern_name="dashboard:case_list", permanent=False), name="home"
    ),
    path("accounts/", include("accounts.urls")),
    path("admin/", admin.site.urls),
    path("health/", include("core.urls")),
    path("imports/", include("imports.urls")),
    path("analysis/", include("analysis.urls")),
    path("", include("dashboard.urls")),
]

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
