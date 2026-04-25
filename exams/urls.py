from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("sessions/", views.session_list, name="session_list"),
    path("sessions/add/", views.session_create, name="session_add"),
    path("sessions/<int:pk>/edit/", views.session_update, name="session_edit"),
    path("sessions/<int:pk>/delete/", views.session_delete, name="session_delete"),
    path("cards/", views.print_cards, name="cards"),
    path("attendance/", views.print_attendance, name="attendance"),
    path("bap/", views.print_bap, name="bap"),
    path("room-label/", views.print_room_label, name="room_label"),
]

