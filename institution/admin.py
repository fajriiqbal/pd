from django.contrib import admin

from .models import SchoolIdentity


@admin.register(SchoolIdentity)
class SchoolIdentityAdmin(admin.ModelAdmin):
    list_display = (
        "institution_name",
        "npsn",
        "district",
        "regency",
        "principal_name",
        "updated_at",
    )
    search_fields = (
        "institution_name",
        "npsn",
        "nsm",
        "district",
        "regency",
        "province",
        "principal_name",
        "operator_name",
    )
    readonly_fields = ("created_at", "updated_at")

