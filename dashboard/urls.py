from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("workflow/", views.workflow, name="workflow"),
    path("health/", views.health, name="health"),
    path("search/", views.search, name="search"),
]
