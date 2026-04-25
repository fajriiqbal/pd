from django.contrib import admin

from .models import ExamSession


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "semester", "start_date", "end_date", "is_active", "updated_at")
    list_filter = ("academic_year", "semester", "is_active")
    search_fields = ("name", "description", "academic_year__name")
    ordering = ("-is_active", "-start_date")

