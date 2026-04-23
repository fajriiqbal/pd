from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import NoReverseMatch, reverse


class CustomUser(AbstractUser):
    REQUIRED_FIELDS = ["email", "full_name"]

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "guru", "Guru"
        STUDENT = "siswa", "Siswa"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True)
    is_school_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = self.username
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name or self.username

    @property
    def profile_url(self):
        try:
            if self.role == self.Role.TEACHER and hasattr(self, "teacher_profile"):
                return reverse("teachers:edit", args=[self.teacher_profile.pk])
            if self.role == self.Role.STUDENT and hasattr(self, "student_profile"):
                return reverse("students:edit", args=[self.student_profile.pk])
        except NoReverseMatch:
            return ""
        return ""


class ActivityLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=80)
    module = models.CharField(max_length=80)
    object_label = models.CharField(max_length=255, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    message = models.CharField(max_length=255, blank=True)
    path = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Log Aktivitas"
        verbose_name_plural = "Log Aktivitas"

    def __str__(self) -> str:
        return f"{self.module} - {self.action} - {self.object_label or self.message}"
