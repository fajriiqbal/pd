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


class ExamScheduleItem(models.Model):
    class ItemType(models.TextChoices):
        EXAM = "exam", "Mapel ujian"
        BREAK = "break", "Istirahat"
        OTHER = "other", "Lainnya"

    session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="schedule_items",
        verbose_name="Sesi ujian",
    )
    exam_date = models.DateField(verbose_name="Tanggal")
    title = models.CharField(max_length=120, verbose_name="Nama kegiatan")
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.EXAM, verbose_name="Jenis")
    start_time = models.TimeField(verbose_name="Jam mulai")
    end_time = models.TimeField(verbose_name="Jam selesai")
    description = models.CharField(max_length=255, blank=True, verbose_name="Keterangan")
    sort_order = models.PositiveSmallIntegerField(default=1, verbose_name="Urutan")
    is_active = models.BooleanField(default=True, verbose_name="Aktif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("exam_date", "start_time", "sort_order", "title")
        verbose_name = "Jadwal Ujian"
        verbose_name_plural = "Jadwal Ujian"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Jam selesai harus setelah jam mulai."})
        if self.session_id and self.exam_date:
            if self.exam_date < self.session.start_date or self.exam_date > self.session.end_date:
                raise ValidationError({"exam_date": "Tanggal jadwal harus berada di dalam rentang sesi ujian."})

    def __str__(self) -> str:
        return f"{self.title} - {self.exam_date}"
