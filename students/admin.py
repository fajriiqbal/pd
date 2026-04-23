from django.contrib import admin

from .models import (
    PromotionRun,
    PromotionRunItem,
    StudentDocument,
    StudentAlumniArchive,
    StudentAlumniDocument,
    StudentAlumniValidation,
    StudentMutationRecord,
    StudentEnrollment,
    StudentProfile,
)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nis", "current_class_display", "family_status", "entry_year", "is_active")
    list_filter = ("study_group", "class_name", "entry_year", "is_active", "gender", "family_status")
    search_fields = ("user__full_name", "user__username", "nis", "nisn", "guardian_name", "father_name", "mother_name")
    autocomplete_fields = ("user", "study_group")

    @admin.display(description="Kelas / Rombel")
    def current_class_display(self, obj):
        return obj.current_class_label


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "academic_year", "study_group", "status")
    list_filter = ("academic_year", "study_group", "status")
    search_fields = ("student__user__full_name", "student__nis", "student__nisn")
    autocomplete_fields = ("student", "study_group", "previous_enrollment")


class PromotionRunItemInline(admin.TabularInline):
    model = PromotionRunItem
    extra = 0
    autocomplete_fields = ("student", "source_study_group", "target_study_group")


@admin.register(PromotionRun)
class PromotionRunAdmin(admin.ModelAdmin):
    list_display = ("source_academic_year", "target_academic_year", "source_school_class", "source_study_group", "status", "created_at")
    list_filter = ("status", "source_academic_year", "target_academic_year", "source_school_class")
    search_fields = ("source_academic_year__name", "target_academic_year__name")
    autocomplete_fields = ("source_school_class", "source_study_group", "created_by")
    inlines = (PromotionRunItemInline,)


@admin.register(PromotionRunItem)
class PromotionRunItemAdmin(admin.ModelAdmin):
    list_display = ("student", "promotion_run", "source_study_group", "target_study_group", "action")
    list_filter = ("action", "promotion_run__source_academic_year", "promotion_run__target_academic_year")
    search_fields = ("student__user__full_name", "student__nis", "student__nisn")
    autocomplete_fields = ("promotion_run", "student", "source_study_group", "target_study_group")


@admin.register(StudentAlumniArchive)
class StudentAlumniArchiveAdmin(admin.ModelAdmin):
    list_display = ("full_name", "nis", "nisn", "class_name", "graduation_year", "graduation_status", "archived_at")
    list_filter = ("graduation_status", "graduation_year")
    search_fields = ("full_name", "nis", "nisn", "class_name")


@admin.register(StudentAlumniDocument)
class StudentAlumniDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "alumni", "document_type", "uploaded_at")
    list_filter = ("document_type",)
    search_fields = ("title", "alumni__full_name")


@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "document_type", "uploaded_at")
    list_filter = ("document_type",)
    search_fields = ("title", "student__user__full_name", "student__nis", "student__nisn")
    autocomplete_fields = ("student",)


@admin.register(StudentAlumniValidation)
class StudentAlumniValidationAdmin(admin.ModelAdmin):
    list_display = ("alumni", "status", "validated_by", "validated_at")
    list_filter = ("status",)
    search_fields = ("alumni__full_name", "alumni__nis", "alumni__nisn", "government_name", "diploma_name")
    autocomplete_fields = ("alumni", "validated_by")


@admin.register(StudentMutationRecord)
class StudentMutationRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "direction", "mutation_date", "created_by")
    list_filter = ("direction", "mutation_date")
    search_fields = ("student__user__full_name", "student__nis", "origin_school_name", "destination_school_name")
    autocomplete_fields = ("student", "origin_study_group", "destination_study_group", "created_by")
