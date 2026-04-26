from django.contrib import admin

from .models import (
    AcademicYear,
    ClassSubject,
    GradeBook,
    PbmScheduleSlot,
    RombelTeachingAssignment,
    SchoolClass,
    StudentGrade,
    StudyGroup,
    Subject,
)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "level_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "school_class",
        "academic_year",
        "homeroom_teacher",
        "capacity",
        "is_active",
    )
    list_filter = ("academic_year", "school_class", "is_active")
    search_fields = ("name", "room_name", "homeroom_teacher__user__full_name")
    autocomplete_fields = ("academic_year", "school_class", "homeroom_teacher")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "curriculum", "category", "sort_order", "is_active")
    list_filter = ("curriculum", "category", "is_active")
    search_fields = ("name", "code", "description")


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ("school_class", "subject", "teacher", "minimum_score", "weekly_hours", "is_active")
    list_filter = ("school_class", "subject__curriculum", "subject__category", "is_active")
    search_fields = ("school_class__name", "subject__name", "teacher__user__full_name")
    autocomplete_fields = ("school_class", "subject", "teacher")


@admin.register(RombelTeachingAssignment)
class RombelTeachingAssignmentAdmin(admin.ModelAdmin):
    list_display = ("study_group", "subject", "teacher", "minimum_score", "weekly_hours", "is_active")
    list_filter = ("study_group__academic_year", "study_group__school_class", "subject__curriculum", "is_active")
    search_fields = ("study_group__name", "study_group__school_class__name", "subject__name", "teacher__user__full_name")
    autocomplete_fields = ("study_group", "subject", "teacher")


@admin.register(PbmScheduleSlot)
class PbmScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ("academic_year", "school_class", "day_of_week", "lesson_order", "class_subject", "teacher", "is_active")
    list_filter = ("academic_year", "school_class", "day_of_week", "is_active")
    search_fields = ("school_class__name", "class_subject__subject__name", "teacher__user__full_name")
    autocomplete_fields = ("academic_year", "school_class", "class_subject", "teacher")


class StudentGradeInline(admin.TabularInline):
    model = StudentGrade
    extra = 0
    autocomplete_fields = ("student",)


@admin.register(GradeBook)
class GradeBookAdmin(admin.ModelAdmin):
    list_display = ("study_group", "class_subject", "semester", "academic_year", "status")
    list_filter = ("academic_year", "semester", "status", "study_group__school_class")
    search_fields = ("study_group__name", "class_subject__subject__name", "academic_year__name")
    autocomplete_fields = ("academic_year", "study_group", "class_subject", "created_by")
    inlines = (StudentGradeInline,)


@admin.register(StudentGrade)
class StudentGradeAdmin(admin.ModelAdmin):
    list_display = ("student", "grade_book", "knowledge_score", "skill_score", "attitude")
    list_filter = ("grade_book__academic_year", "grade_book__semester", "grade_book__class_subject__subject")
    search_fields = ("student__user__full_name", "student__nis", "grade_book__class_subject__subject__name")
    autocomplete_fields = ("grade_book", "student")
