from django.urls import path

from . import views

app_name = "academics"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("curriculum/", views.curriculum_dashboard, name="curriculum"),
    path("curriculum/structure/", views.curriculum_structure, name="curriculum_structure"),
    path("years/", views.year_list, name="year_list"),
    path("years/add/", views.academic_year_create, name="year_add"),
    path("years/<int:pk>/edit/", views.academic_year_update, name="year_edit"),
    path("years/<int:pk>/delete/", views.academic_year_delete, name="year_delete"),
    path("subjects/", views.subject_list, name="subject_list"),
    path("subjects/add/", views.subject_create, name="subject_add"),
    path("subjects/<int:pk>/edit/", views.subject_update, name="subject_edit"),
    path("subjects/<int:pk>/delete/", views.subject_delete, name="subject_delete"),
    path("class-subjects/add/", views.class_subject_create, name="class_subject_add"),
    path("class-subjects/<int:pk>/edit/", views.class_subject_update, name="class_subject_edit"),
    path("class-subjects/<int:pk>/delete/", views.class_subject_delete, name="class_subject_delete"),
    path("ledgers/", views.ledger_list, name="ledger_list"),
    path("ledgers/add/", views.ledger_create, name="ledger_add"),
    path("ledgers/<int:pk>/", views.ledger_detail, name="ledger_detail"),
    path("classes/add/", views.school_class_create, name="class_add"),
    path("classes/<int:pk>/", views.school_class_detail, name="class_detail"),
    path("classes/<int:pk>/edit/", views.school_class_update, name="class_edit"),
    path("classes/<int:pk>/delete/", views.school_class_delete, name="class_delete"),
    path("study-groups/add/", views.study_group_create, name="group_add"),
    path("study-groups/<int:pk>/", views.study_group_detail, name="group_detail"),
    path("study-groups/<int:pk>/report/", views.group_report, name="group_report"),
    path("study-groups/<int:pk>/edit/", views.study_group_update, name="group_edit"),
    path("study-groups/<int:pk>/delete/", views.study_group_delete, name="group_delete"),
]
