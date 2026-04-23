from django.urls import path

from . import api

urlpatterns = [
    path("subjects/", api.subject_collection, name="api_subject_list"),
    path("subjects/categories/", api.subject_categories, name="api_subject_categories"),
    path("subjects/<int:pk>/", api.subject_detail, name="api_subject_detail"),
]
