from django.core.exceptions import ValidationError
from django.db import models

from academics.models import AcademicYear


class ExamSession(models.Model):
    class Semester(models.TextChoices):
        ODD = "ganjil", "Ganjil"
        EVEN = "genap", "Genap"

    name = models.CharField(max_length=120, verbose_name="Nama sesi ujian")
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="exam_sessions",
        verbose_name="Tahun ajaran",
    )
    semester = models.CharField(max_length=10, choices=Semester.choices, verbose_name="Semester")
    start_date = models.DateField(verbose_name="Tanggal mulai")
    end_date = models.DateField(verbose_name="Tanggal selesai")
    description = models.TextField(blank=True, verbose_name="Keterangan")
    is_active = models.BooleanField(default=False, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_active", "-start_date", "-created_at")
        verbose_name = "Sesi Ujian"
        verbose_name_plural = "Sesi Ujian"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Tanggal selesai harus sama atau setelah tanggal mulai."})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            type(self).objects.exclude(pk=self.pk).update(is_active=False)

    def __str__(self) -> str:
        return f"{self.name} - {self.academic_year.name}"

