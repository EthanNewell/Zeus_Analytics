from django.urls import path

from . import views

app_name = "imports"
urlpatterns = [path("", views.upload, name="upload")]
