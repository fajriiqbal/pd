from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ActivityLog, CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        "username",
        "full_name",
        "role",
        "is_staff",
        "is_school_active",
        "is_active",
    )
    list_filter = ("role", "is_staff", "is_active", "is_school_active")
    search_fields = ("username", "full_name", "email", "phone_number")
    ordering = ("username",)

    fieldsets = UserAdmin.fieldsets + (
        (
            "Informasi Madrasah",
            {
                "fields": (
                    "full_name",
                    "role",
                    "phone_number",
                    "is_school_active",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Informasi Madrasah",
            {
                "fields": (
                    "full_name",
                    "role",
                    "phone_number",
                    "is_school_active",
                )
            },
        ),
    )


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "module", "action", "object_label", "actor", "path")
    list_filter = ("module", "action", "created_at")
    search_fields = ("module", "action", "object_label", "object_id", "message", "actor__username", "actor__full_name")
    readonly_fields = ("actor", "action", "module", "object_label", "object_id", "message", "path", "created_at")
    ordering = ("-created_at",)
