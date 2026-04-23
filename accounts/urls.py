from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.user_list, name="list"),
    path("add/", views.user_create, name="add"),
    path("<int:pk>/edit/", views.user_update, name="edit"),
    path("<int:pk>/password/", views.user_password_update, name="password"),
    path("<int:pk>/delete/", views.user_delete, name="delete"),
]
