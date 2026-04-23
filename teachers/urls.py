from django.urls import path

from . import views

app_name = "teachers"

urlpatterns = [
    path("", views.teacher_list, name="list"),
    path("reference-schools/", views.school_reference_search, name="school_reference_search"),
    path("mutations/", views.teacher_mutation_list, name="mutation_list"),
    path("mutations/add/", views.teacher_mutation_create, name="mutation_add"),
    path("archives/", views.teacher_archive_list, name="archive_list"),
    path("teaching-assignments/", views.teaching_assignment_list, name="teaching_assignments"),
    path("teaching-assignments/add/", views.teaching_assignment_create, name="teaching_assignment_add"),
    path("teaching-assignments/<int:pk>/edit/", views.teaching_assignment_update, name="teaching_assignment_edit"),
    path("teaching-assignments/<int:pk>/delete/", views.teaching_assignment_delete, name="teaching_assignment_delete"),
    path("additional-tasks/", views.additional_task_list, name="additional_tasks"),
    path("additional-tasks/add/", views.additional_task_create, name="additional_task_add"),
    path("additional-tasks/<int:pk>/edit/", views.additional_task_update, name="additional_task_edit"),
    path("additional-tasks/<int:pk>/delete/", views.additional_task_delete, name="additional_task_delete"),
    path("import/template/", views.teacher_import_template, name="import_template"),
    path("import/preview/", views.teacher_import_preview, name="import_preview"),
    path("import/execute/", views.teacher_import_execute, name="import_execute"),
    path("add/", views.teacher_create, name="add"),
    path("<int:pk>/edit/", views.teacher_update, name="edit"),
    path("<int:pk>/education/add/", views.teacher_education_add, name="education_add"),
    path("<int:pk>/education/<int:education_pk>/edit/", views.teacher_education_update, name="education_edit"),
    path("<int:pk>/education/<int:education_pk>/delete/", views.teacher_education_delete, name="education_delete"),
    path("<int:pk>/delete/", views.teacher_delete, name="delete"),
]
