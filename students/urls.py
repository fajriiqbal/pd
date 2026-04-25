from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("", views.student_list, name="list"),
    path("backup/", views.backup_restore, name="backup_restore"),
    path("mutations/", views.student_mutation_list, name="mutation_list"),
    path("mutations/add/", views.student_mutation_create, name="mutation_add"),
    path("mutations/<int:pk>/letter/", views.student_mutation_letter, name="mutation_letter"),
    path("alumni/", views.alumni_list, name="alumni_list"),
    path("alumni/<int:pk>/", views.alumni_detail, name="alumni_detail"),
    path("alumni/<int:pk>/validation/", views.alumni_validation_update, name="alumni_validation_update"),
    path("alumni/validations/", views.alumni_validation_list, name="alumni_validation_list"),
    path("alumni/<int:pk>/documents/add/", views.alumni_document_add, name="alumni_document_add"),
    path("alumni/<int:pk>/documents/<int:document_pk>/delete/", views.alumni_document_delete, name="alumni_document_delete"),
    path("import/preview/", views.student_import_preview, name="import_preview"),
    path("import/execute/", views.student_import_execute, name="import_execute"),
    path("promotions/", views.promotion_list, name="promotion_list"),
    path("promotions/create/", views.promotion_create, name="promotion_create"),
    path("promotions/<int:pk>/", views.promotion_detail, name="promotion_detail"),
    path("promotions/<int:pk>/execute/", views.promotion_execute, name="promotion_execute"),
    path("promotions/<int:pk>/delete/", views.promotion_delete, name="promotion_delete"),
    path("add/", views.student_create, name="add"),
    path("bulk-delete/", views.student_bulk_delete, name="bulk_delete"),
    path("<int:pk>/", views.student_detail, name="detail"),
    path("<int:pk>/edit/", views.student_update, name="edit"),
    path("<int:pk>/attachments/<int:document_pk>/delete/", views.student_attachment_delete, name="attachment_delete"),
    path("<int:pk>/delete/", views.student_delete, name="delete"),
]
