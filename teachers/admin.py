from django.contrib import admin

from .models import TeacherAdditionalTask, TeacherArchive, TeacherEducationHistory, TeacherMutationRecord, TeacherProfile


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nip", "subject", "employment_status", "is_active")
    list_filter = ("employment_status", "is_active", "gender")
    search_fields = ("user__full_name", "user__username", "nip", "subject")
    autocomplete_fields = ("user",)


@admin.register(TeacherAdditionalTask)
class TeacherAdditionalTaskAdmin(admin.ModelAdmin):
    list_display = ("teacher", "name", "task_type", "hours_per_week", "start_date", "end_date", "is_active")
    list_filter = ("task_type", "is_active")
    search_fields = ("teacher__user__full_name", "name", "description")
    autocomplete_fields = ("teacher",)


@admin.register(TeacherEducationHistory)
class TeacherEducationHistoryAdmin(admin.ModelAdmin):
    list_display = ("teacher", "degree_level", "institution_name", "institution_npsn", "graduation_year", "is_highest_degree")
    list_filter = ("degree_level", "is_highest_degree")
    search_fields = ("teacher__user__full_name", "institution_name", "institution_npsn", "major")
    autocomplete_fields = ("teacher",)


@admin.register(TeacherArchive)
class TeacherArchiveAdmin(admin.ModelAdmin):
    list_display = ("full_name", "nip", "nuptk", "exit_status", "archived_at")
    list_filter = ("exit_status", "employment_status")
    search_fields = ("full_name", "nip", "nuptk", "subject")
    autocomplete_fields = ("teacher",)


@admin.register(TeacherMutationRecord)
class TeacherMutationRecordAdmin(admin.ModelAdmin):
    list_display = ("teacher", "direction", "mutation_date", "created_by")
    list_filter = ("direction", "mutation_date", "exit_status")
    search_fields = ("teacher__user__full_name", "teacher__nip", "origin_school_name", "destination_school_name")
    autocomplete_fields = ("teacher", "created_by")
