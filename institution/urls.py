from django.urls import path

from . import views

app_name = "institution"

urlpatterns = [
    path("setup/", views.setup, name="setup"),
]

