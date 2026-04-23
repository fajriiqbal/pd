from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TeacherProfile(models.Model):
    class Gender(models.TextChoices):
        MALE = "L", "Laki-laki"
        FEMALE = "P", "Perempuan"

    class EmploymentStatus(models.TextChoices):
        PERMANENT = "tetap", "Tetap"
        HONORARY = "honorer", "Honorer"
        CONTRACT = "kontrak", "Kontrak"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    nip = models.CharField(max_length=30, unique=True, blank=True, null=True)
    nik = models.CharField(max_length=30, unique=True, blank=True, null=True)
    nuptk = models.CharField(max_length=30, unique=True, blank=True, null=True)
    subject = models.CharField(max_length=100, blank=True)
    task = models.CharField(max_length=150, blank=True)
    placement = models.CharField(max_length=150, blank=True)
    total_jtm = models.PositiveIntegerField(default=0)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    birth_place = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    hire_date = models.DateField(null=True, blank=True)
    madrasah_email = models.EmailField(blank=True)
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.PERMANENT,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__full_name",)
        verbose_name = "Data Guru"
        verbose_name_plural = "Data Guru"

    def __str__(self) -> str:
        return f"{self.user.full_name} - {self.nip or 'NIP belum diisi'}"

    def save(self, *args, **kwargs):
        self.nip = self.nip or None
        self.nik = self.nik or None
        self.nuptk = self.nuptk or None
        super().save(*args, **kwargs)


class TeacherAdditionalTask(models.Model):
    class TaskType(models.TextChoices):
        HOMEROOM = "wali_kelas", "Wali kelas"
        LEADERSHIP = "pimpinan", "Pimpinan/koordinator"
        EXTRACURRICULAR = "ekskul", "Pembina ekstrakurikuler"
        PICKET = "piket", "Piket guru"
        LABRARY = "lab_perpus", "Laboratorium/perpustakaan"
        ADMINISTRATION = "administrasi", "Administrasi madrasah"
        OTHER = "lainnya", "Lainnya"

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="additional_tasks",
    )
    name = models.CharField(max_length=150)
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.OTHER)
    description = models.CharField(max_length=255, blank=True)
    hours_per_week = models.PositiveSmallIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("teacher__user__full_name", "task_type", "name")
        verbose_name = "Tugas Tambahan Guru"
        verbose_name_plural = "Tugas Tambahan Guru"

    def __str__(self) -> str:
        return f"{self.teacher.user.full_name} - {self.name}"


class TeacherEducationHistory(models.Model):
    class DegreeLevel(models.TextChoices):
        SMA = "sma", "SMA/SMK/MA"
        D3 = "d3", "D3"
        S1 = "s1", "S1"
        S2 = "s2", "S2"
        S3 = "s3", "S3"
        OTHER = "lainnya", "Lainnya"

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="education_histories",
    )
    degree_level = models.CharField(max_length=20, choices=DegreeLevel.choices, default=DegreeLevel.S1)
    institution_name = models.CharField(max_length=150)
    institution_npsn = models.CharField(max_length=20, blank=True)
    institution_level = models.CharField(max_length=50, blank=True)
    institution_status = models.CharField(max_length=50, blank=True)
    institution_address = models.CharField(max_length=255, blank=True)
    institution_source_url = models.URLField(blank=True)
    major = models.CharField(max_length=120, blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    certificate_number = models.CharField(max_length=100, blank=True)
    certificate_file = models.FileField(upload_to="teacher_diplomas/", blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True)
    is_highest_degree = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("teacher__user__full_name", "-graduation_year", "degree_level")
        verbose_name = "Riwayat Pendidikan Guru"
        verbose_name_plural = "Riwayat Pendidikan Guru"

    def __str__(self) -> str:
        return f"{self.teacher.user.full_name} - {self.get_degree_level_display()} {self.institution_name}"


class TeacherArchive(models.Model):
    class ExitStatus(models.TextChoices):
        PENSIONED = "pensioned", "Pensiun"
        TRANSFERRED = "transferred", "Pindah"
        OTHER = "other", "Lainnya"

    teacher = models.OneToOneField(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archive",
    )
    full_name = models.CharField(max_length=150)
    nip = models.CharField(max_length=30, blank=True)
    nik = models.CharField(max_length=30, blank=True)
    nuptk = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=100, blank=True)
    task = models.CharField(max_length=150, blank=True)
    placement = models.CharField(max_length=150, blank=True)
    total_jtm = models.PositiveIntegerField(default=0)
    gender = models.CharField(max_length=1, choices=TeacherProfile.Gender.choices)
    birth_place = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    hire_date = models.DateField(null=True, blank=True)
    madrasah_email = models.EmailField(blank=True)
    employment_status = models.CharField(max_length=20, choices=TeacherProfile.EmploymentStatus.choices)
    exit_status = models.CharField(max_length=20, choices=ExitStatus.choices, default=ExitStatus.OTHER)
    exit_notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-archived_at", "full_name")
        verbose_name = "Arsip Guru"
        verbose_name_plural = "Arsip Guru"

    def __str__(self) -> str:
        return f"{self.full_name} - {self.get_exit_status_display()}"


class TeacherMutationRecord(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Mutasi masuk"
        OUTBOUND = "outbound", "Mutasi keluar"

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="mutation_records",
    )
    direction = models.CharField(max_length=20, choices=Direction.choices)
    mutation_date = models.DateField()
    origin_school_name = models.CharField(max_length=150, blank=True)
    destination_school_name = models.CharField(max_length=150, blank=True)
    origin_placement = models.CharField(max_length=150, blank=True)
    destination_placement = models.CharField(max_length=150, blank=True)
    exit_status = models.CharField(max_length=20, choices=TeacherArchive.ExitStatus.choices, blank=True)
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    supporting_document = models.FileField(upload_to="teacher_mutations/", blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_mutation_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-mutation_date", "-created_at")
        verbose_name = "Mutasi Guru"
        verbose_name_plural = "Mutasi Guru"

    def __str__(self) -> str:
        return f"{self.teacher.user.full_name} - {self.get_direction_display()}"

    def clean(self):
        if self.direction == self.Direction.INBOUND and not (self.origin_school_name):
            raise ValidationError({"origin_school_name": "Sekolah asal wajib diisi untuk mutasi masuk."})
        if self.direction == self.Direction.OUTBOUND:
            if not self.destination_school_name:
                raise ValidationError({"destination_school_name": "Sekolah tujuan wajib diisi untuk mutasi keluar."})
            if not self.exit_status:
                raise ValidationError({"exit_status": "Keterangan keluar wajib diisi untuk guru yang keluar."})
