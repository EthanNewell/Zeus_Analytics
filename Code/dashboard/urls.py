from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("cases/", views.cases, name="case_list"),
    path("cases/<uuid:case_id>/", views.case_detail, name="case_detail"),
    path("cases/<uuid:case_id>/reviews/", views.review_create, name="review_create"),
    path("exports/cases.csv", views.case_export, name="case_export"),
    path(
        "evidence/<uuid:evidence_id>/download/", views.evidence_download, name="evidence_download"
    ),
]
