from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from academics.models import SchoolClass


class StudentProfile(models.Model):
    class Gender(models.TextChoices):
        MALE = "L", "Laki-laki"
        FEMALE = "P", "Perempuan"

    class FamilyStatus(models.TextChoices):
        COMPLETE = "lengkap", "Lengkap"
        ORPHAN_FATHER = "yatim", "Yatim"
        ORPHAN_MOTHER = "piatu", "Piatu"
        ORPHAN_BOTH = "yatim_piatu", "Yatim piatu"
        UNDER_GUARDIAN = "wali", "Diasuh wali"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    nis = models.CharField(max_length=30, unique=True, blank=True, null=True)
    nisn = models.CharField(max_length=30, unique=True, blank=True, null=True)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    birth_place = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    father_name = models.CharField(max_length=150, blank=True)
    father_nik = models.CharField(max_length=20, blank=True, default="")
    father_birth_place = models.CharField(max_length=100, blank=True, default="")
    father_birth_date = models.DateField(null=True, blank=True)
    father_education = models.CharField(max_length=100, blank=True, default="")
    father_job = models.CharField(max_length=120, blank=True, default="")
    mother_name = models.CharField(max_length=150, blank=True)
    mother_nik = models.CharField(max_length=20, blank=True, default="")
    mother_birth_place = models.CharField(max_length=100, blank=True, default="")
    mother_birth_date = models.DateField(null=True, blank=True)
    mother_education = models.CharField(max_length=100, blank=True, default="")
    mother_job = models.CharField(max_length=120, blank=True, default="")
    guardian_name = models.CharField(max_length=150, blank=True)
    family_status = models.CharField(max_length=20, choices=FamilyStatus.choices, blank=True, default="")
    special_needs = models.CharField(max_length=150, blank=True)
    disability_notes = models.CharField(max_length=150, blank=True)
    kip_number = models.CharField(max_length=50, blank=True)
    class_name = models.CharField(max_length=100, help_text="Contoh: 9A, 10 IPA 1, atau XI Keagamaan")
    study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    entry_year = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__full_name",)
        verbose_name = "Data Siswa"
        verbose_name_plural = "Data Siswa"

    def __str__(self) -> str:
        return f"{self.user.full_name} - {self.nis or 'NIS belum diisi'}"

    def save(self, *args, **kwargs):
        self.nis = self.nis or None
        self.nisn = self.nisn or None
        if not self.nis:
            generated_nis = self._generate_nis()
            if generated_nis:
                self.nis = generated_nis
        super().save(*args, **kwargs)

    def _effective_entry_year(self) -> int | None:
        if self.study_group_id and self.study_group and self.study_group.school_class_id:
            level_order = self.study_group.school_class.level_order
            academic_year = getattr(self.study_group, "academic_year", None)
            base_year = int(str(academic_year.start_date)[:4]) if academic_year and academic_year.start_date else None

            if base_year and 7 <= level_order <= 9:
                return base_year - max(level_order - 7, 0)

        return self.entry_year or None

    def _generate_nis(self) -> str | None:
        effective_entry_year = self._effective_entry_year()
        if not effective_entry_year:
            return None

        from institution.models import SchoolIdentity

        identity = SchoolIdentity.objects.first()
        prefix_root = (identity.nsm if identity and identity.nsm else "").strip()
        if not prefix_root:
            return None

        prefix = f"{prefix_root}{int(effective_entry_year) % 100:02d}"

        existing_numbers = []
        for existing_nis in (
            StudentProfile.objects.exclude(pk=self.pk)
            .exclude(nis__isnull=True)
            .exclude(nis="")
            .filter(nis__startswith=prefix)
            .values_list("nis", flat=True)
        ):
            suffix = str(existing_nis)[len(prefix):]
            if suffix.isdigit():
                existing_numbers.append(int(suffix))

        next_number = (max(existing_numbers) if existing_numbers else 0) + 1
        return f"{prefix}{next_number:04d}"

    @property
    def current_class_label(self) -> str:
        if self.study_group_id:
            return self.study_group.name
        return self.class_name


class StudentAlumniArchive(models.Model):
    class GraduationStatus(models.TextChoices):
        GRADUATED = "graduated", "Lulus"
        TRANSFERRED = "transferred", "Mutasi"
        OTHER = "other", "Lainnya"

    student = models.OneToOneField(
        StudentProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alumni_archive",
    )
    full_name = models.CharField(max_length=150)
    nis = models.CharField(max_length=30, blank=True)
    nisn = models.CharField(max_length=30, blank=True)
    gender = models.CharField(max_length=1, choices=StudentProfile.Gender.choices)
    birth_place = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    father_name = models.CharField(max_length=150, blank=True)
    father_nik = models.CharField(max_length=20, blank=True, default="")
    father_birth_place = models.CharField(max_length=100, blank=True, default="")
    father_birth_date = models.DateField(null=True, blank=True)
    father_education = models.CharField(max_length=100, blank=True, default="")
    father_job = models.CharField(max_length=120, blank=True, default="")
    mother_name = models.CharField(max_length=150, blank=True)
    mother_nik = models.CharField(max_length=20, blank=True, default="")
    mother_birth_place = models.CharField(max_length=100, blank=True, default="")
    mother_birth_date = models.DateField(null=True, blank=True)
    mother_education = models.CharField(max_length=100, blank=True, default="")
    mother_job = models.CharField(max_length=120, blank=True, default="")
    guardian_name = models.CharField(max_length=150, blank=True)
    family_status = models.CharField(max_length=20, blank=True, default="")
    special_needs = models.CharField(max_length=150, blank=True)
    disability_notes = models.CharField(max_length=150, blank=True)
    kip_number = models.CharField(max_length=50, blank=True)
    class_name = models.CharField(max_length=100, blank=True)
    entry_year = models.PositiveIntegerField(null=True, blank=True)
    graduation_year = models.PositiveIntegerField(null=True, blank=True)
    graduation_status = models.CharField(max_length=20, choices=GraduationStatus.choices, default=GraduationStatus.GRADUATED)
    graduation_notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-graduation_year", "full_name")
        verbose_name = "Data Alumni"
        verbose_name_plural = "Data Alumni"

    def __str__(self) -> str:
        return f"{self.full_name} - {self.get_graduation_status_display()}"


class StudentAlumniDocument(models.Model):
    class DocumentType(models.TextChoices):
        DIPLOMA = "ijazah", "Ijazah"
        REPORT_CARD = "rapor", "Rapor"
        FAMILY_CARD = "kk", "Kartu Keluarga"
        BIRTH_CERTIFICATE = "akte", "Akta Kelahiran"
        ID_CARD = "ktp", "KTP"
        OTHER = "lainnya", "Lainnya"

    alumni = models.ForeignKey(
        StudentAlumniArchive,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, default=DocumentType.OTHER)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to="alumni_documents/")
    notes = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("document_type", "-uploaded_at")
        verbose_name = "Dokumen Alumni"
        verbose_name_plural = "Dokumen Alumni"

    def __str__(self) -> str:
        return f"{self.alumni.full_name} - {self.title}"


class StudentDocument(models.Model):
    class DocumentType(models.TextChoices):
        FAMILY_CARD = "kk", "Kartu Keluarga"
        BIRTH_CERTIFICATE = "akte", "Akta Kelahiran"
        DIPLOMA = "ijazah", "Ijazah"
        REPORT_CARD = "rapor", "Rapor"
        KIP_PIP = "kip_pip", "KIP/PIP"
        OTHER = "lainnya", "Lainnya"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, default=DocumentType.OTHER)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to="student_documents/")
    notes = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("document_type", "-uploaded_at")
        verbose_name = "Berkas Siswa"
        verbose_name_plural = "Berkas Siswa"

    def __str__(self) -> str:
        return f"{self.student.user.full_name} - {self.title}"


class StudentAlumniValidation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Belum divalidasi"
        MATCH = "match", "Cocok"
        REVIEW = "review", "Perlu revisi"
        MISMATCH = "mismatch", "Tidak cocok"

    alumni = models.OneToOneField(
        StudentAlumniArchive,
        on_delete=models.CASCADE,
        related_name="validation",
    )
    government_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Nama sesuai sistem pemerintah atau data referensi resmi.",
    )
    government_nisn = models.CharField(
        max_length=30,
        blank=True,
        help_text="NISN sesuai data sistem yang dijadikan pembanding.",
    )
    government_birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Tanggal lahir sesuai data sistem yang dijadikan pembanding.",
    )
    government_father_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Nama ayah sesuai data sistem yang dijadikan pembanding.",
    )
    diploma_name = models.CharField(max_length=150, blank=True)
    family_card_name = models.CharField(max_length=150, blank=True)
    birth_certificate_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alumni_validations",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-validated_at", "-created_at")
        verbose_name = "Validasi Alumni"
        verbose_name_plural = "Validasi Alumni"

    def __str__(self) -> str:
        return f"{self.alumni.full_name} - {self.get_status_display()}"

    @staticmethod
    def normalize_name(value: str) -> str:
        return " ".join((value or "").split()).strip().casefold()

    def calculate_status(self) -> str:
        reference_values = [
            self.government_name,
            self.government_nisn,
            self.government_birth_date,
            self.government_father_name,
        ]
        if not any(value for value in reference_values):
            return self.Status.PENDING

        checks = [
            self.normalize_name(self.government_name) == self.normalize_name(self.alumni.full_name),
            self.normalize_name(self.government_nisn) == self.normalize_name(self.alumni.nisn),
            self.government_birth_date == self.alumni.birth_date,
            self.normalize_name(self.government_father_name) == self.normalize_name(self.alumni.father_name),
        ]

        if all(checks):
            return self.Status.MATCH

        if not checks[0] or not checks[1]:
            return self.Status.MISMATCH

        return self.Status.REVIEW

    def save(self, *args, **kwargs):
        self.status = self.calculate_status()
        super().save(*args, **kwargs)


class StudentMutationRecord(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Mutasi masuk"
        OUTBOUND = "outbound", "Mutasi keluar"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="mutation_records",
    )
    direction = models.CharField(max_length=20, choices=Direction.choices)
    mutation_date = models.DateField()
    origin_school_name = models.CharField(max_length=150, blank=True)
    origin_school_npsn = models.CharField(max_length=20, blank=True)
    destination_school_name = models.CharField(max_length=150, blank=True)
    destination_school_npsn = models.CharField(max_length=20, blank=True)
    origin_study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_mutations_as_origin",
    )
    destination_study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_mutations_as_destination",
    )
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    supporting_document = models.FileField(upload_to="student_mutations/", blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_mutation_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-mutation_date", "-created_at")
        verbose_name = "Mutasi Siswa"
        verbose_name_plural = "Mutasi Siswa"

    def __str__(self) -> str:
        return f"{self.student.user.full_name} - {self.get_direction_display()}"

    def clean(self):
        if self.direction == self.Direction.INBOUND and not (self.origin_school_name or self.origin_school_npsn):
            raise ValidationError({"origin_school_name": "Sekolah asal wajib diisi untuk mutasi masuk."})
        if self.direction == self.Direction.OUTBOUND and not (self.destination_school_name or self.destination_school_npsn):
            raise ValidationError({"destination_school_name": "Sekolah tujuan wajib diisi untuk mutasi keluar."})


class StudentEnrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktif"
        REPEATED = "repeated", "Tinggal kelas"
        GRADUATED = "graduated", "Lulus"
        TRANSFERRED = "transferred", "Mutasi"
        INACTIVE = "inactive", "Tidak aktif"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="student_enrollments",
    )
    study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_enrollments",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    previous_enrollment = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_enrollments",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("academic_year__start_date", "student__user__full_name")
        verbose_name = "Riwayat Penempatan Siswa"
        verbose_name_plural = "Riwayat Penempatan Siswa"
        constraints = [
            models.UniqueConstraint(
                fields=("student", "academic_year"),
                name="unique_student_enrollment_per_year",
            )
        ]

    def __str__(self) -> str:
        group_label = self.study_group.name if self.study_group_id else self.get_status_display()
        return f"{self.student.user.full_name} - {group_label} ({self.academic_year.name})"

    def clean(self):
        if self.study_group_id and self.academic_year_id != self.study_group.academic_year_id:
            raise ValidationError({"study_group": "Rombel harus berada pada tahun ajaran yang sama."})


class PromotionRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        EXECUTED = "executed", "Sudah dijalankan"

    source_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="promotion_runs_as_source",
    )
    target_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="promotion_runs_as_target",
    )
    source_school_class = models.ForeignKey(
        "academics.SchoolClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotion_runs",
    )
    source_study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotion_runs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_runs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Proses Kenaikan Kelas"
        verbose_name_plural = "Proses Kenaikan Kelas"

    def __str__(self) -> str:
        return f"Kenaikan {self.source_academic_year.name} ke {self.target_academic_year.name}"

    def clean(self):
        if self.source_academic_year_id == self.target_academic_year_id:
            terminal_class = self.source_school_class
            if self.source_study_group_id:
                terminal_class = self.source_study_group.school_class

            if not terminal_class:
                raise ValidationError({"target_academic_year": "Pilih kelas terminal jika ingin memakai tahun ajaran yang sama."})

            next_school_class = SchoolClass.objects.filter(
                level_order__gt=terminal_class.level_order,
                is_active=True,
            ).exists()
            if next_school_class:
                raise ValidationError({"target_academic_year": "Tahun ajaran tujuan harus berbeda, kecuali untuk kelas terminal seperti kelas 9."})
        if self.source_study_group_id and self.source_study_group.academic_year_id != self.source_academic_year_id:
            raise ValidationError({"source_study_group": "Rombel asal harus sesuai tahun ajaran asal."})
        if self.source_study_group_id and self.source_school_class_id:
            if self.source_study_group.school_class_id != self.source_school_class_id:
                raise ValidationError({"source_study_group": "Rombel asal harus sesuai kelas asal."})


class PromotionRunItem(models.Model):
    class Action(models.TextChoices):
        PROMOTE = "promote", "Naik kelas"
        REPEAT = "repeat", "Tinggal kelas"
        GRADUATE = "graduate", "Lulus"
        TRANSFER = "transfer", "Mutasi"
        INACTIVE = "inactive", "Tidak aktif"

    promotion_run = models.ForeignKey(
        PromotionRun,
        on_delete=models.CASCADE,
        related_name="items",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="promotion_items",
    )
    source_study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotion_items_as_source",
    )
    target_study_group = models.ForeignKey(
        "academics.StudyGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotion_items_as_target",
    )
    action = models.CharField(max_length=20, choices=Action.choices, default=Action.PROMOTE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("student__user__full_name",)
        verbose_name = "Detail Kenaikan Kelas"
        verbose_name_plural = "Detail Kenaikan Kelas"
        constraints = [
            models.UniqueConstraint(
                fields=("promotion_run", "student"),
                name="unique_student_per_promotion_run",
            )
        ]

    def __str__(self) -> str:
        return f"{self.student.user.full_name} - {self.get_action_display()}"

    def clean(self):
        if self.source_study_group_id:
            if self.source_study_group.academic_year_id != self.promotion_run.source_academic_year_id:
                raise ValidationError({"source_study_group": "Rombel asal harus sesuai tahun ajaran asal."})
        if self.target_study_group_id:
            if self.target_study_group.academic_year_id != self.promotion_run.target_academic_year_id:
                raise ValidationError({"target_study_group": "Rombel tujuan harus sesuai tahun ajaran tujuan."})
        if self.action in {self.Action.PROMOTE, self.Action.REPEAT} and not self.target_study_group_id:
            raise ValidationError({"target_study_group": "Rombel tujuan wajib diisi untuk siswa naik atau tinggal kelas."})
