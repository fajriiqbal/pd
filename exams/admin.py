from django.contrib import admin

from .models import ExamScheduleItem, ExamSession


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "semester", "start_date", "end_date", "is_active", "updated_at")
    list_filter = ("academic_year", "semester", "is_active")
    search_fields = ("name", "description", "academic_year__name")
    ordering = ("-is_active", "-start_date")


@admin.register(ExamScheduleItem)
class ExamScheduleItemAdmin(admin.ModelAdmin):
    list_display = ("session", "exam_date", "title", "item_type", "start_time", "end_time", "is_active")
    list_filter = ("session", "item_type", "is_active", "exam_date")
    search_fields = ("title", "description", "session__name", "session__academic_year__name")
    ordering = ("exam_date", "start_time", "sort_order")
