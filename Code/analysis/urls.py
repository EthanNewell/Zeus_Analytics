from django.urls import path

from . import views

app_name = "analysis"
urlpatterns = [path("run/", views.run, name="run")]
