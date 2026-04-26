from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from teachers.models import TeacherProfile


class AcademicYear(models.Model):
    name = models.CharField(max_length=30, unique=True, help_text="Contoh: 2026/2027")
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "Tahun Ajaran"
        verbose_name_plural = "Tahun Ajaran"

    def clean(self):
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "Tanggal selesai harus setelah tanggal mulai."})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            AcademicYear.objects.exclude(pk=self.pk).update(is_active=False)

    def __str__(self) -> str:
        return self.name


class SchoolClass(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Contoh: Kelas 7, Kelas 8, XI Keagamaan")
    level_order = models.PositiveSmallIntegerField(default=1, help_text="Urutan kelas untuk tampilan")
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("level_order", "name")
        verbose_name = "Kelas"
        verbose_name_plural = "Kelas"

    def __str__(self) -> str:
        return self.name


class StudyGroup(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="study_groups",
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name="study_groups",
    )
    name = models.CharField(max_length=100, help_text="Contoh: 7A, 8B, XI Keagamaan 1")
    homeroom_teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homeroom_groups",
    )
    capacity = models.PositiveIntegerField(default=32)
    room_name = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("school_class__level_order", "name")
        verbose_name = "Rombel"
        verbose_name_plural = "Rombel"
        constraints = [
            models.UniqueConstraint(
                fields=("academic_year", "name"),
                name="unique_study_group_per_year",
            )
        ]

    def clean(self):
        if self.homeroom_teacher_id:
            duplicate_teacher = StudyGroup.objects.filter(
                academic_year=self.academic_year,
                homeroom_teacher=self.homeroom_teacher,
            ).exclude(pk=self.pk)
            if duplicate_teacher.exists():
                raise ValidationError(
                    {"homeroom_teacher": "Guru ini sudah menjadi wali kelas pada tahun ajaran yang sama."}
                )

    def __str__(self) -> str:
        return f"{self.name} - {self.academic_year.name}"

    @property
    def student_count(self) -> int:
        return self.students.filter(is_active=True).count()


class Subject(models.Model):
    class Curriculum(models.TextChoices):
        SHARED = "lintas", "Lintas kurikulum"
        K13 = "k13", "Kurikulum 2013"
        MERDEKA = "merdeka", "Kurikulum Merdeka"

    class Category(models.TextChoices):
        RELIGION = "agama", "Keagamaan"
        GENERAL = "umum", "Umum"
        LOCAL = "lokal", "Muatan lokal"
        DEVELOPMENT = "pengembangan", "Pengembangan diri"

    curriculum = models.CharField(max_length=20, choices=Curriculum.choices, default=Curriculum.SHARED)
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, blank=True, null=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("curriculum", "sort_order", "name")
        verbose_name = "Mata Pelajaran"
        verbose_name_plural = "Mata Pelajaran"
        constraints = [
            models.UniqueConstraint(
                fields=("curriculum", "name"),
                name="unique_subject_name_per_curriculum",
            ),
            models.UniqueConstraint(
                fields=("curriculum", "code"),
                condition=models.Q(code__isnull=False),
                name="unique_subject_code_per_curriculum",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code or None
        super().save(*args, **kwargs)


class ClassSubject(models.Model):
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_subjects",
    )
    minimum_score = models.PositiveSmallIntegerField(default=75)
    weekly_hours = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("school_class__level_order", "subject__sort_order", "subject__name")
        verbose_name = "Mapel Per Kelas"
        verbose_name_plural = "Mapel Per Kelas"
        constraints = [
            models.UniqueConstraint(
                fields=("school_class", "subject"),
                name="unique_subject_per_school_class",
            )
        ]

    def __str__(self) -> str:
        return f"{self.school_class.name} - {self.subject.name}"


class PbmScheduleSlot(models.Model):
    class DayOfWeek(models.TextChoices):
        MONDAY = "1", "Senin"
        TUESDAY = "2", "Selasa"
        WEDNESDAY = "3", "Rabu"
        THURSDAY = "4", "Kamis"
        FRIDAY = "5", "Jumat"
        SATURDAY = "6", "Sabtu"

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="pbm_schedule_slots",
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name="pbm_schedule_slots",
    )
    day_of_week = models.CharField(max_length=1, choices=DayOfWeek.choices)
    lesson_order = models.PositiveSmallIntegerField(verbose_name="Jam ke-")
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.PROTECT,
        related_name="pbm_schedule_slots",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pbm_schedule_slots",
    )
    room_name = models.CharField(max_length=100, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("school_class__level_order", "day_of_week", "lesson_order")
        verbose_name = "Slot Jadwal PBM"
        verbose_name_plural = "Slot Jadwal PBM"
        constraints = [
            models.UniqueConstraint(
                fields=("academic_year", "school_class", "day_of_week", "lesson_order"),
                name="unique_pbm_slot_per_class_day_order",
            )
        ]

    def clean(self):
        if self.class_subject_id and self.school_class_id:
            if self.class_subject.school_class_id != self.school_class_id:
                raise ValidationError({"class_subject": "Mapel harus sesuai kelas yang dipilih."})
        if self.teacher_id and self.class_subject_id:
            if self.class_subject.teacher_id and self.teacher_id != self.class_subject.teacher_id:
                raise ValidationError({"teacher": "Guru pengampu sebaiknya sama dengan mapel kelas yang dipilih."})
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Jam selesai harus setelah jam mulai."})

    def save(self, *args, **kwargs):
        if not self.teacher_id and self.class_subject_id:
            self.teacher = self.class_subject.teacher
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.school_class.name} - {self.get_day_of_week_display()} Jam {self.lesson_order}"


class GradeBook(models.Model):
    class Semester(models.TextChoices):
        ODD = "ganjil", "Ganjil"
        EVEN = "genap", "Genap"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        LOCKED = "locked", "Dikunci"

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="grade_books",
    )
    study_group = models.ForeignKey(
        StudyGroup,
        on_delete=models.PROTECT,
        related_name="grade_books",
    )
    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.PROTECT,
        related_name="grade_books",
    )
    semester = models.CharField(max_length=10, choices=Semester.choices, default=Semester.ODD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_books",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = (
            "-academic_year__start_date",
            "semester",
            "study_group__school_class__level_order",
            "study_group__name",
            "class_subject__subject__sort_order",
        )
        verbose_name = "Ledger Nilai"
        verbose_name_plural = "Ledger Nilai"
        constraints = [
            models.UniqueConstraint(
                fields=("study_group", "class_subject", "semester"),
                name="unique_grade_book_per_group_subject_semester",
            )
        ]

    def __str__(self) -> str:
        return f"{self.study_group.name} - {self.class_subject.subject.name} ({self.get_semester_display()})"

    def clean(self):
        if self.study_group_id and self.academic_year_id:
            if self.study_group.academic_year_id != self.academic_year_id:
                raise ValidationError({"study_group": "Rombel harus berada pada tahun ajaran yang dipilih."})
        if self.study_group_id and self.class_subject_id:
            if self.study_group.school_class_id != self.class_subject.school_class_id:
                raise ValidationError({"class_subject": "Mapel harus sesuai kelas rombel."})

    @property
    def subject(self):
        return self.class_subject.subject


class StudentGrade(models.Model):
    class Attitude(models.TextChoices):
        A = "A", "Sangat baik"
        B = "B", "Baik"
        C = "C", "Cukup"
        D = "D", "Perlu pembinaan"

    grade_book = models.ForeignKey(
        GradeBook,
        on_delete=models.CASCADE,
        related_name="student_grades",
    )
    student = models.ForeignKey(
        "students.StudentProfile",
        on_delete=models.CASCADE,
        related_name="grades",
    )
    knowledge_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    skill_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    attitude = models.CharField(max_length=1, choices=Attitude.choices, blank=True)
    teacher_notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("student__user__full_name",)
        verbose_name = "Nilai Siswa"
        verbose_name_plural = "Nilai Siswa"
        constraints = [
            models.UniqueConstraint(
                fields=("grade_book", "student"),
                name="unique_student_grade_per_grade_book",
            )
        ]

    def __str__(self) -> str:
        return f"{self.student.user.full_name} - {self.grade_book}"

    @property
    def final_score(self):
        scores = [score for score in [self.knowledge_score, self.skill_score] if score is not None]
        if not scores:
            return None
        average = sum(scores, Decimal("0")) / Decimal(len(scores))
        return average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def is_complete(self) -> bool:
        return self.knowledge_score is not None and self.skill_score is not None and bool(self.attitude)

    @property
    def passed_minimum(self) -> bool:
        return self.final_score is not None and self.final_score >= self.grade_book.class_subject.minimum_score

    def clean(self):
        if self.student_id and self.grade_book_id:
            if self.student.study_group_id != self.grade_book.study_group_id:
                raise ValidationError({"student": "Siswa harus berada pada rombel ledger nilai."})
