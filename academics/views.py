import random
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CustomUser
from students.models import StudentProfile
from teachers.models import TeacherProfile

from .curriculum import SUBJECT_PRESETS
from .forms import (
    AcademicYearCreateForm,
    AcademicYearForm,
    ClassSubjectForm,
    GradeBookForm,
    PbmScheduleGeneratorForm,
    PbmScheduleSlotForm,
    SchoolClassForm,
    StudyGroupForm,
    SubjectForm,
)
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


def _sync_grade_book_students(grade_book):
    students = grade_book.study_group.students.filter(is_active=True).select_related("user").order_by("user__full_name")
    for student in students:
        StudentGrade.objects.get_or_create(grade_book=grade_book, student=student)


def _group_suffix(group_name):
    match = re.search(r"([A-Za-z]+)$", group_name.strip())
    return match.group(1).upper() if match else ""


def _next_school_class(source_class):
    return SchoolClass.objects.filter(
        level_order__gt=source_class.level_order,
        is_active=True,
    ).order_by("level_order", "name").first()


def _clone_study_group_name(source_group, target_school_class):
    target_name = target_school_class.name.strip()
    if target_name.lower().startswith("kelas "):
        target_name = target_name[6:].strip()

    suffix = _group_suffix(source_group.name)
    if not suffix:
        return target_name or source_group.name
    if target_name.endswith(suffix):
        return target_name
    if target_name and target_name[-1].isalnum():
        return f"{target_name}{suffix}"
    return f"{target_name} {suffix}"


def _clone_study_groups_from_previous_year(target_academic_year):
    source_year = (
        AcademicYear.objects.filter(start_date__lt=target_academic_year.start_date)
        .order_by("-start_date")
        .first()
    )
    if not source_year:
        return {"source_year": None, "created": 0}

    source_groups = StudyGroup.objects.select_related(
        "school_class",
        "homeroom_teacher",
    ).filter(
        academic_year=source_year,
        is_active=True,
    ).order_by("school_class__level_order", "name")

    created_count = 0
    for source_group in source_groups:
        target_school_class = _next_school_class(source_group.school_class)
        if not target_school_class:
            continue

        group_name = _clone_study_group_name(source_group, target_school_class)
        _, created = StudyGroup.objects.get_or_create(
            academic_year=target_academic_year,
            name=group_name,
            defaults={
                "school_class": target_school_class,
                "homeroom_teacher": source_group.homeroom_teacher,
                "capacity": source_group.capacity,
                "room_name": source_group.room_name,
                "notes": source_group.notes,
                "is_active": source_group.is_active,
            },
        )
        if created:
            created_count += 1

    return {"source_year": source_year, "created": created_count}


def _parse_score(value):
    value = value.strip()
    if not value:
        return None
    try:
        score = Decimal(value)
    except InvalidOperation:
        raise ValueError("Nilai harus berupa angka.")
    if score < 0 or score > 100:
        raise ValueError("Nilai harus berada di antara 0 sampai 100.")
    return score


def _build_pbm_day_blocks(
    start_time,
    end_time,
    lesson_duration_minutes,
    first_break_after_lessons,
    second_break_after_lessons,
    break_duration_minutes,
):
    lesson_duration = timedelta(minutes=lesson_duration_minutes)
    break_duration = timedelta(minutes=break_duration_minutes)
    current = datetime.combine(datetime.today().date(), start_time)
    end = datetime.combine(datetime.today().date(), end_time)
    blocks = []
    lesson_order = 1
    lessons_since_first_break = 0
    first_break_done = False
    second_break_done = False
    second_break_target = (first_break_after_lessons or 0) + (second_break_after_lessons or 0)

    while current + lesson_duration <= end:
        lesson_start = current
        lesson_end = current + lesson_duration
        blocks.append(
            {
                "kind": "lesson",
                "lesson_order": lesson_order,
                "start_time": lesson_start.time(),
                "end_time": lesson_end.time(),
            }
        )
        current = lesson_end
        lesson_order += 1
        lessons_since_first_break += 1

        if not first_break_done and first_break_after_lessons and lessons_since_first_break >= first_break_after_lessons:
            if current + break_duration > end:
                break
            break_start = current
            break_end = current + break_duration
            blocks.append(
                {
                    "kind": "break",
                    "label": "Istirahat",
                    "notes": f"Istirahat {break_duration_minutes} menit",
                    "start_time": break_start.time(),
                    "end_time": break_end.time(),
                }
            )
            current = break_end
            first_break_done = True
            lessons_since_first_break = 0
            continue

        if first_break_done and not second_break_done and second_break_target and lesson_order - 1 >= second_break_target:
            if current + break_duration > end:
                break
            break_start = current
            break_end = current + break_duration
            blocks.append(
                {
                    "kind": "break",
                    "label": "Istirahat",
                    "notes": f"Istirahat {break_duration_minutes} menit",
                    "start_time": break_start.time(),
                    "end_time": break_end.time(),
                }
            )
            current = break_end
            second_break_done = True
            lessons_since_first_break = 0

    return blocks


def _teacher_has_pbm_conflict(teacher, academic_year, day_value, start_time, end_time, school_class):
    if not teacher:
        return False

    return PbmScheduleSlot.objects.filter(
        teacher=teacher,
        academic_year=academic_year,
        day_of_week=day_value,
        is_active=True,
    ).exclude(
        school_class=school_class,
    ).filter(
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).exists()


def _build_pbm_preview_payload(cleaned_data, seed):
    school_class = cleaned_data["school_class"]
    academic_year = cleaned_data["academic_year"]
    class_subjects = list(
        ClassSubject.objects.select_related("subject", "teacher__user")
        .filter(school_class=school_class, is_active=True)
        .order_by("subject__sort_order", "subject__name")
    )
    subject_pool = []
    for class_subject in class_subjects:
        subject_pool.extend([class_subject] * int(class_subject.weekly_hours or 0))

    rng = random.Random(seed)
    if cleaned_data.get("randomize"):
        rng.shuffle(subject_pool)

    lesson_blocks_by_day = {}
    for day_value, day_label in PbmScheduleSlot.DayOfWeek.choices:
        lesson_blocks_by_day[day_value] = {
            "day_value": day_value,
            "day_label": day_label,
            "rows": _build_pbm_day_blocks(
                cleaned_data["start_time"],
                cleaned_data["end_time"],
                cleaned_data["lesson_duration_minutes"],
                cleaned_data["first_break_after_lessons"],
                cleaned_data["second_break_after_lessons"],
                cleaned_data["break_duration_minutes"],
            ),
        }

    assigned_count = 0
    conflict_count = 0
    for day_value in lesson_blocks_by_day:
        for row in lesson_blocks_by_day[day_value]["rows"]:
            row["start_time"] = row["start_time"].strftime("%H:%M")
            row["end_time"] = row["end_time"].strftime("%H:%M")
            if row["kind"] != "lesson":
                continue

            start_time = datetime.strptime(row["start_time"], "%H:%M").time()
            end_time = datetime.strptime(row["end_time"], "%H:%M").time()

            selected_index = None
            for index, class_subject in enumerate(subject_pool):
                if _teacher_has_pbm_conflict(
                    class_subject.teacher,
                    academic_year,
                    day_value,
                    start_time,
                    end_time,
                    school_class,
                ):
                    continue
                selected_index = index
                break

            class_subject = subject_pool.pop(selected_index) if selected_index is not None else None
            if class_subject:
                assigned_count += 1
                row["class_subject_id"] = class_subject.pk
                row["class_subject_name"] = class_subject.subject.name
                row["teacher_name"] = (
                    class_subject.teacher.user.full_name
                    if class_subject.teacher and class_subject.teacher.user_id
                    else ""
                )
                row["room_name"] = ""
                row["notes"] = ""
            else:
                conflict_count += 1
                row["class_subject_id"] = None
                row["class_subject_name"] = None
                row["teacher_name"] = ""
                row["room_name"] = ""
                row["notes"] = "Tidak ada mapel yang aman pada slot ini."

    payload = {
        "token": uuid4().hex,
        "seed": seed,
        "settings": {
            "academic_year_id": academic_year.pk,
            "academic_year_name": academic_year.name,
            "school_class_id": school_class.pk,
            "school_class_name": school_class.name,
            "start_time": cleaned_data["start_time"].strftime("%H:%M"),
            "end_time": cleaned_data["end_time"].strftime("%H:%M"),
            "lesson_duration_minutes": cleaned_data["lesson_duration_minutes"],
            "first_break_after_lessons": cleaned_data["first_break_after_lessons"],
            "second_break_after_lessons": cleaned_data["second_break_after_lessons"],
            "break_duration_minutes": cleaned_data["break_duration_minutes"],
            "randomize": bool(cleaned_data.get("randomize")),
            "overwrite_existing": bool(cleaned_data.get("overwrite_existing")),
        },
        "days": list(lesson_blocks_by_day.values()),
        "subject_pool_count": sum(int(class_subject.weekly_hours or 0) for class_subject in class_subjects),
        "filled_lesson_count": assigned_count,
        "unfilled_lesson_count": conflict_count + len(subject_pool),
        "conflict_count": conflict_count,
    }
    return payload


def _save_pbm_preview_payload(payload):
    settings_data = payload["settings"]
    academic_year = AcademicYear.objects.get(pk=settings_data["academic_year_id"])
    school_class = SchoolClass.objects.get(pk=settings_data["school_class_id"])

    if settings_data.get("overwrite_existing"):
        PbmScheduleSlot.objects.filter(
            academic_year=academic_year,
            school_class=school_class,
            is_active=True,
        ).delete()

    created_slots = []
    for day in payload["days"]:
        for row in day["rows"]:
            if row["kind"] != "lesson" or not row.get("class_subject_id"):
                continue
            class_subject = ClassSubject.objects.select_related("teacher").get(pk=row["class_subject_id"])
            created_slots.append(
                PbmScheduleSlot(
                    academic_year=academic_year,
                    school_class=school_class,
                    day_of_week=day["day_value"],
                    lesson_order=row["lesson_order"],
                    start_time=datetime.strptime(row["start_time"], "%H:%M").time(),
                    end_time=datetime.strptime(row["end_time"], "%H:%M").time(),
                    class_subject=class_subject,
                    teacher=class_subject.teacher,
                    room_name=row.get("room_name", ""),
                    notes=row.get("notes", ""),
                    is_active=True,
                )
            )

    PbmScheduleSlot.objects.bulk_create(created_slots)
    return len(created_slots)


def _report_rows(study_group, semester):
    class_subjects = list(
        ClassSubject.objects.select_related("subject", "teacher__user")
        .filter(school_class=study_group.school_class, is_active=True)
        .order_by("subject__sort_order", "subject__name")
    )
    grade_books = {
        grade_book.class_subject_id: grade_book
        for grade_book in GradeBook.objects.filter(
            study_group=study_group,
            semester=semester,
        ).select_related("class_subject", "class_subject__subject")
    }
    grades_by_book = {}
    if grade_books:
        grades = StudentGrade.objects.filter(grade_book__in=grade_books.values()).select_related("student")
        for grade in grades:
            grades_by_book[(grade.grade_book_id, grade.student_id)] = grade

    students = list(study_group.students.select_related("user").filter(is_active=True).order_by("user__full_name"))
    rows = []
    for student in students:
        subject_grades = []
        total_score = Decimal("0")
        scored_subjects = 0
        complete_count = 0
        for class_subject in class_subjects:
            grade_book = grade_books.get(class_subject.pk)
            grade = grades_by_book.get((grade_book.pk, student.pk)) if grade_book else None
            final_score = grade.final_score if grade else None
            if final_score is not None:
                total_score += final_score
                scored_subjects += 1
            if grade and grade.is_complete:
                complete_count += 1
            subject_grades.append(
                {
                    "class_subject": class_subject,
                    "grade_book": grade_book,
                    "grade": grade,
                    "final_score": final_score,
                }
            )
        rows.append(
            {
                "student": student,
                "subject_grades": subject_grades,
                "average": (total_score / scored_subjects).quantize(Decimal("0.01")) if scored_subjects else None,
                "complete_count": complete_count,
                "subject_count": len(class_subjects),
            }
        )
    return class_subjects, rows


@login_required
def overview(request):
    query = request.GET.get("q", "").strip()

    classes = (
        SchoolClass.objects.annotate(active_group_count=Count("study_groups", distinct=True))
        .order_by("level_order", "name")
    )
    study_groups = StudyGroup.objects.select_related(
        "academic_year",
        "school_class",
        "homeroom_teacher__user",
    ).prefetch_related("students__user")

    if query:
        classes = classes.filter(Q(name__icontains=query) | Q(description__icontains=query))
        study_groups = study_groups.filter(
            Q(name__icontains=query)
            | Q(school_class__name__icontains=query)
            | Q(academic_year__name__icontains=query)
            | Q(homeroom_teacher__user__full_name__icontains=query)
        )

    context = {
        "query": query,
        "classes": classes,
        "study_groups": study_groups,
        "class_count": SchoolClass.objects.count(),
        "study_group_count": StudyGroup.objects.count(),
        "homeroom_count": StudyGroup.objects.filter(homeroom_teacher__isnull=False).count(),
    }
    return render(request, "academics/overview.html", context)


@login_required
def curriculum_dashboard(request):
    query = request.GET.get("q", "").strip()
    class_subject_qs = (
        ClassSubject.objects.select_related("subject", "teacher__user")
        .filter(is_active=True)
        .order_by("subject__sort_order", "subject__name")
    )
    classes = (
        SchoolClass.objects.annotate(
            active_group_count=Count("study_groups", filter=Q(study_groups__is_active=True), distinct=True),
            active_class_subject_count=Count("class_subjects", filter=Q(class_subjects__is_active=True), distinct=True),
            assigned_teacher_count=Count(
                "class_subjects__teacher",
                filter=Q(class_subjects__is_active=True, class_subjects__teacher__isnull=False),
                distinct=True,
            ),
            total_weekly_hours=Sum("class_subjects__weekly_hours", filter=Q(class_subjects__is_active=True)),
        )
        .prefetch_related(Prefetch("class_subjects", queryset=class_subject_qs))
        .order_by("level_order", "name")
    )

    if query:
        classes = classes.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(class_subjects__subject__name__icontains=query)
            | Q(class_subjects__teacher__user__full_name__icontains=query)
        ).distinct()

    subject_stats = {
        item["curriculum"]: item
        for item in Subject.objects.values("curriculum").annotate(
            total=Count("id"),
            active_total=Count("id", filter=Q(is_active=True)),
        )
    }
    curriculum_breakdown = [
        {
            "label": label,
            "key": key,
            "total": subject_stats.get(key, {}).get("total", 0),
            "active_total": subject_stats.get(key, {}).get("active_total", 0),
        }
        for key, label in Subject.Curriculum.choices
        if key != Subject.Curriculum.SHARED
    ]
    steps = [
        {
            "title": "Master mapel",
            "description": "Pilih katalog mapel K13, Merdeka, atau mapel khusus agar struktur mudah dipakai ulang.",
            "url": "academics:subject_list",
        },
        {
            "title": "Struktur kurikulum",
            "description": "Hubungkan mapel dengan kelas, guru pengampu, KKM, dan jam pelajaran.",
            "url": "academics:curriculum_structure",
        },
        {
            "title": "Beban guru",
            "description": "Pastikan setiap pengampu memiliki beban JTM yang jelas sebelum jadwal disusun.",
            "url": "teachers:teaching_assignments",
        },
        {
            "title": "Rekap jam PBM",
            "description": "Lihat total JTM per guru sebelum disusun menjadi jadwal mingguan.",
            "url": "academics:curriculum_teacher_hours",
        },
        {
            "title": "Jadwal PBM",
            "description": "Gunakan struktur tersebut untuk menyusun jadwal belajar mengajar mingguan.",
            "url": "academics:pbm_schedule_list",
        },
    ]
    context = {
        "query": query,
        "steps": steps,
        "classes": classes,
        "subject_stats": subject_stats,
        "curriculum_breakdown": curriculum_breakdown,
        "class_count": SchoolClass.objects.filter(is_active=True).count(),
        "active_subject_count": Subject.objects.filter(is_active=True).count(),
        "class_subject_count": ClassSubject.objects.filter(is_active=True).count(),
        "assigned_teacher_count": ClassSubject.objects.filter(is_active=True, teacher__isnull=False).values("teacher").distinct().count(),
        "total_weekly_hours": ClassSubject.objects.filter(is_active=True).aggregate(total=Sum("weekly_hours"))["total"] or 0,
    }
    return render(request, "academics/curriculum_dashboard.html", context)


@login_required
def curriculum_structure(request):
    query = request.GET.get("q", "").strip()
    class_subject_qs = (
        ClassSubject.objects.select_related("subject", "teacher__user")
        .filter(is_active=True)
        .order_by("subject__sort_order", "subject__name")
    )
    classes = (
        SchoolClass.objects.annotate(
            active_group_count=Count("study_groups", filter=Q(study_groups__is_active=True), distinct=True),
            active_class_subject_count=Count("class_subjects", filter=Q(class_subjects__is_active=True), distinct=True),
            total_weekly_hours=Sum("class_subjects__weekly_hours", filter=Q(class_subjects__is_active=True)),
        )
        .prefetch_related(Prefetch("class_subjects", queryset=class_subject_qs))
        .order_by("level_order", "name")
    )

    if query:
        classes = classes.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(class_subjects__subject__name__icontains=query)
            | Q(class_subjects__teacher__user__full_name__icontains=query)
        ).distinct()

    return render(
        request,
        "academics/curriculum_structure.html",
        {
            "query": query,
            "classes": classes,
            "class_count": SchoolClass.objects.filter(is_active=True).count(),
            "class_subject_count": ClassSubject.objects.filter(is_active=True).count(),
            "teacher_count": ClassSubject.objects.filter(is_active=True, teacher__isnull=False).values("teacher").distinct().count(),
            "total_weekly_hours": ClassSubject.objects.filter(is_active=True).aggregate(total=Sum("weekly_hours"))["total"] or 0,
        },
    )


@login_required
def school_class_detail(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    study_groups = (
        StudyGroup.objects.filter(school_class=school_class)
        .select_related("academic_year", "homeroom_teacher__user")
        .annotate(
            total_students=Count("students", distinct=True),
            active_students=Count("students", filter=Q(students__is_active=True), distinct=True),
        )
        .order_by("-academic_year__start_date", "name")
    )
    active_year = AcademicYear.objects.filter(is_active=True).first()
    active_groups = study_groups.filter(academic_year=active_year) if active_year else study_groups.none()
    active_students = StudentProfile.objects.filter(
        is_active=True,
        study_group__school_class=school_class,
    )
    students_without_nis = active_students.filter(Q(nis__isnull=True) | Q(nis="")).count()
    groups_without_homeroom = study_groups.filter(homeroom_teacher__isnull=True).count()

    context = {
        "school_class": school_class,
        "study_groups": study_groups,
        "active_year": active_year,
        "active_group_count": active_groups.count(),
        "total_group_count": study_groups.count(),
        "active_student_count": active_students.count(),
        "students_without_nis": students_without_nis,
        "groups_without_homeroom": groups_without_homeroom,
        "academic_tools": [
            {
                "title": "Raport kelas",
                "description": "Nantinya menjadi pintu masuk rekap nilai, catatan wali kelas, dan cetak raport per rombel.",
                "status": "Tersedia",
                "url_name": "academics:ledger_list",
            },
            {
                "title": "Mata pelajaran",
                "description": "Atur mapel, guru pengampu, KKM, dan jam pelajaran untuk kelas ini.",
                "status": "Tersedia",
                "url_name": "academics:subject_list",
            },
            {
                "title": "Ledger nilai",
                "description": "Tempat kontrol nilai mapel sebelum ditarik ke raport akhir semester.",
                "status": "Tersedia",
                "url_name": "academics:ledger_list",
            },
        ],
    }
    return render(request, "academics/class_detail.html", context)


@login_required
def study_group_detail(request, pk):
    study_group = get_object_or_404(
        StudyGroup.objects.select_related(
            "academic_year",
            "school_class",
            "homeroom_teacher__user",
        ),
        pk=pk,
    )
    teacher_profile = getattr(request.user, "teacher_profile", None)
    if not (
        request.user.is_superuser
        or request.user.role == CustomUser.Role.ADMIN
        or (
            request.user.role == CustomUser.Role.TEACHER
            and teacher_profile
            and study_group.homeroom_teacher_id == teacher_profile.id
        )
    ):
        raise PermissionDenied
    students = study_group.students.select_related("user").order_by("user__full_name")
    active_students = students.filter(is_active=True)
    can_edit_students = bool(
        request.user.is_superuser
        or request.user.role == CustomUser.Role.ADMIN
        or (request.user.role == CustomUser.Role.TEACHER and teacher_profile and study_group.homeroom_teacher_id == teacher_profile.id)
    )
    active_student_count = active_students.count()
    inactive_student_count = students.filter(is_active=False).count()
    male_count = active_students.filter(gender=StudentProfile.Gender.MALE).count()
    female_count = active_students.filter(gender=StudentProfile.Gender.FEMALE).count()
    missing_nis_count = active_students.filter(Q(nis__isnull=True) | Q(nis="")).count()
    missing_nisn_count = active_students.filter(Q(nisn__isnull=True) | Q(nisn="")).count()
    capacity_percent = min(round((active_student_count / study_group.capacity) * 100), 100) if study_group.capacity else 0
    available_seats = max(study_group.capacity - active_student_count, 0)

    context = {
        "study_group": study_group,
        "students": students,
        "can_edit_students": can_edit_students,
        "active_student_count": active_student_count,
        "inactive_student_count": inactive_student_count,
        "male_count": male_count,
        "female_count": female_count,
        "missing_nis_count": missing_nis_count,
        "missing_nisn_count": missing_nisn_count,
        "capacity_percent": capacity_percent,
        "available_seats": available_seats,
        "academic_tools": [
            {
                "title": "Raport rombel",
                "description": "Pusat cetak raport, catatan wali kelas, dan status kelengkapan nilai siswa.",
                "status": "Tersedia",
                "url": f"/academics/study-groups/{study_group.pk}/report/",
            },
            {
                "title": "Ledger nilai",
                "description": "Kontrol input nilai mapel sebelum disahkan ke raport semester.",
                "status": "Tersedia",
                "url_name": "academics:ledger_list",
            },
            {
                "title": "Mata pelajaran",
                "description": "Kelola mapel kelas, guru pengampu, KKM, dan jam pelajaran.",
                "status": "Tersedia",
                "url_name": "academics:subject_list",
            },
            {
                "title": "Kenaikan kelas",
                "description": "Jalur cepat menuju proses kenaikan kelas saat akhir tahun ajaran.",
                "status": "Tersedia",
                "url_name": "students:promotion_list",
            },
        ],
    }
    return render(request, "academics/study_group_detail.html", context)


@login_required
def subject_list(request):
    query = request.GET.get("q", "").strip()
    curriculum = request.GET.get("curriculum", "").strip()
    subjects = Subject.objects.all().order_by("sort_order", "name")
    class_subjects = ClassSubject.objects.select_related(
        "school_class",
        "subject",
        "teacher__user",
    ).order_by("school_class__level_order", "subject__sort_order", "subject__name")

    if query:
        subjects = subjects.filter(Q(name__icontains=query) | Q(code__icontains=query))
        class_subjects = class_subjects.filter(
            Q(subject__name__icontains=query)
            | Q(subject__code__icontains=query)
            | Q(school_class__name__icontains=query)
            | Q(teacher__user__full_name__icontains=query)
        )
    if curriculum:
        subjects = subjects.filter(curriculum=curriculum)
        class_subjects = class_subjects.filter(subject__curriculum=curriculum)

    context = {
        "query": query,
        "selected_curriculum": curriculum,
        "curriculum_choices": Subject.Curriculum.choices,
        "subjects": subjects,
        "class_subjects": class_subjects,
        "subject_count": Subject.objects.count(),
        "active_subject_count": Subject.objects.filter(is_active=True).count(),
        "k13_subject_count": Subject.objects.filter(curriculum=Subject.Curriculum.K13).count(),
        "merdeka_subject_count": Subject.objects.filter(curriculum=Subject.Curriculum.MERDEKA).count(),
        "class_subject_count": ClassSubject.objects.count(),
        "unassigned_subject_count": ClassSubject.objects.filter(teacher__isnull=True).count(),
    }
    return render(request, "academics/subject_list.html", context)


@login_required
def subject_create(request):
    form = SubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mata pelajaran berhasil ditambahkan.")
        return redirect("academics:subject_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": "Tambah mata pelajaran",
            "page_description": "Masukkan master mapel yang akan dipakai pada kurikulum kelas dan ledger nilai.",
            "submit_label": "Simpan mapel",
            "cancel_url": "academics:subject_list",
            "checkbox_fields": ["is_active"],
            "subject_presets": SUBJECT_PRESETS,
        },
    )


@login_required
def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    form = SubjectForm(request.POST or None, instance=subject)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mata pelajaran berhasil diperbarui.")
        return redirect("academics:subject_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": f"Edit mata pelajaran {subject.name}",
            "page_description": "Perbarui nama, kategori, kode, atau urutan mapel.",
            "submit_label": "Update mapel",
            "cancel_url": "academics:subject_list",
            "checkbox_fields": ["is_active"],
            "subject_presets": SUBJECT_PRESETS,
        },
    )


@login_required
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if subject.class_subjects.exists():
        messages.error(request, "Mata pelajaran tidak bisa dihapus karena sudah dipakai pada kelas.")
        return redirect("academics:subject_list")

    if request.method == "POST":
        subject.delete()
        messages.success(request, "Mata pelajaran berhasil dihapus.")
        return redirect("academics:subject_list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": subject.name,
            "item_type": "mata pelajaran",
            "cancel_url": "academics:subject_list",
        },
    )


@login_required
def class_subject_create(request):
    form = ClassSubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mapel kelas berhasil ditambahkan.")
        return redirect("academics:subject_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Kurikulum Kelas",
            "page_title": "Tambah mapel per kelas",
            "page_description": "Hubungkan mata pelajaran dengan kelas, guru pengampu, KKM, dan jam pelajaran.",
            "submit_label": "Simpan mapel kelas",
            "cancel_url": "academics:subject_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def class_subject_update(request, pk):
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    form = ClassSubjectForm(request.POST or None, instance=class_subject)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mapel kelas berhasil diperbarui.")
        return redirect("academics:subject_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Kurikulum Kelas",
            "page_title": f"Edit {class_subject}",
            "page_description": "Perbarui guru pengampu, KKM, atau jam pelajaran.",
            "submit_label": "Update mapel kelas",
            "cancel_url": "academics:subject_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def class_subject_delete(request, pk):
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    if class_subject.grade_books.exists():
        messages.error(request, "Mapel kelas tidak bisa dihapus karena sudah memiliki ledger nilai.")
        return redirect("academics:subject_list")

    if request.method == "POST":
        class_subject.delete()
        messages.success(request, "Mapel kelas berhasil dihapus.")
        return redirect("academics:subject_list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": str(class_subject),
            "item_type": "mapel per kelas",
            "cancel_url": "academics:subject_list",
        },
    )


@login_required
def pbm_schedule_list(request):
    query = request.GET.get("q", "").strip()
    year_id = request.GET.get("year", "").strip()
    class_id = request.GET.get("class", "").strip()

    slots = PbmScheduleSlot.objects.select_related(
        "academic_year",
        "school_class",
        "class_subject__subject",
        "class_subject__teacher__user",
        "teacher__user",
    ).filter(is_active=True)

    if year_id:
        slots = slots.filter(academic_year_id=year_id)
    if class_id:
        slots = slots.filter(school_class_id=class_id)
    if query:
        slots = slots.filter(
            Q(school_class__name__icontains=query)
            | Q(class_subject__subject__name__icontains=query)
            | Q(class_subject__teacher__user__full_name__icontains=query)
            | Q(teacher__user__full_name__icontains=query)
        )

    academic_years = AcademicYear.objects.order_by("-start_date")
    school_classes = SchoolClass.objects.filter(is_active=True).order_by("level_order", "name")
    grouped_rows = []
    for school_class in school_classes:
        class_slots = slots.filter(school_class=school_class)
        if not class_slots.exists():
            continue
        day_groups = []
        for day_value, day_label in PbmScheduleSlot.DayOfWeek.choices:
            day_slots = list(class_slots.filter(day_of_week=day_value).order_by("lesson_order"))
            if day_slots:
                day_groups.append({"label": day_label, "items": day_slots})
        grouped_rows.append(
            {
                "school_class": school_class,
                "day_groups": day_groups,
                "total_weekly_hours": class_slots.aggregate(total=Sum("class_subject__weekly_hours"))["total"] or 0,
            }
        )

    return render(
        request,
        "academics/pbm_schedule_list.html",
        {
            "query": query,
            "academic_years": academic_years,
            "school_classes": school_classes,
            "selected_year": year_id,
            "selected_class": class_id,
            "grouped_rows": grouped_rows,
            "slot_count": slots.count(),
            "class_count": len(grouped_rows),
        },
    )


@login_required
def pbm_schedule_create(request):
    form = PbmScheduleSlotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Slot jadwal PBM berhasil ditambahkan.")
        return redirect("academics:pbm_schedule_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Jadwal PBM",
            "page_title": "Tambah slot jadwal PBM",
            "page_description": "Isi slot mingguan untuk kelas, mapel, guru, dan jam ke-.",
            "submit_label": "Simpan slot",
            "cancel_url": "academics:pbm_schedule_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def pbm_schedule_update(request, pk):
    slot = get_object_or_404(PbmScheduleSlot, pk=pk)
    form = PbmScheduleSlotForm(request.POST or None, instance=slot)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Slot jadwal PBM berhasil diperbarui.")
        return redirect("academics:pbm_schedule_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Jadwal PBM",
            "page_title": f"Edit slot {slot}",
            "page_description": "Perbarui jam, mapel, guru, atau kelas untuk slot mingguan ini.",
            "submit_label": "Simpan perubahan",
            "cancel_url": "academics:pbm_schedule_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def pbm_schedule_delete(request, pk):
    slot = get_object_or_404(PbmScheduleSlot, pk=pk)
    if request.method == "POST":
        slot.delete()
        messages.success(request, "Slot jadwal PBM berhasil dihapus.")
        return redirect("academics:pbm_schedule_list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": str(slot),
            "item_type": "slot jadwal PBM",
            "cancel_url": "academics:pbm_schedule_list",
        },
    )


@login_required
def pbm_schedule_generate(request):
    session_key = "pbm_schedule_preview"
    preview_payload = request.session.get(session_key)

    if request.method == "POST" and request.POST.get("action") == "save":
        preview_token = request.POST.get("preview_token", "")
        if not preview_payload:
            messages.error(request, "Belum ada preview jadwal untuk disimpan.")
            return redirect("academics:pbm_schedule_generate")
        if preview_payload.get("token") != preview_token:
            messages.error(request, "Preview jadwal sudah berubah. Generate ulang dulu sebelum menyimpan.")
            return redirect("academics:pbm_schedule_generate")

        created_count = _save_pbm_preview_payload(preview_payload)
        request.session.pop(session_key, None)
        messages.success(request, f"Jadwal PBM otomatis berhasil disimpan dengan {created_count} slot.")
        return redirect("academics:pbm_schedule_list")

    form = PbmScheduleGeneratorForm(request.POST or None)
    if request.method == "POST" and request.POST.get("action") in {"generate", "regenerate"}:
        if form.is_valid():
            seed = (preview_payload or {}).get("seed", 0) + 1
            if request.POST.get("action") == "generate" and not preview_payload:
                seed = 1
            preview_payload = _build_pbm_preview_payload(form.cleaned_data, seed)
            request.session[session_key] = preview_payload
            messages.success(request, "Preview jadwal berhasil dibuat. Anda bisa generate ulang sampai urutannya cocok.")
        else:
            preview_payload = None

    if preview_payload and not form.is_bound:
        form = PbmScheduleGeneratorForm(initial=preview_payload["settings"])
        form.fields["academic_year"].initial = preview_payload["settings"]["academic_year_id"]
        form.fields["school_class"].initial = preview_payload["settings"]["school_class_id"]

    context = {
        "form": form,
        "preview": preview_payload,
        "preview_token": preview_payload["token"] if preview_payload else "",
    }
    return render(request, "academics/pbm_schedule_generate.html", context)


@login_required
def curriculum_teacher_hours(request):
    query = request.GET.get("q", "").strip()
    school_class_id = request.GET.get("class", "").strip()

    teachers = TeacherProfile.objects.select_related("user").annotate(
        active_assignment_count=Count("rombel_assignments", filter=Q(rombel_assignments__is_active=True), distinct=True),
        total_weekly_hours=Sum("rombel_assignments__weekly_hours", filter=Q(rombel_assignments__is_active=True)),
    ).filter(is_active=True)

    if query:
        teachers = teachers.filter(
            Q(user__full_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(nip__icontains=query)
            | Q(subject__icontains=query)
            | Q(rombel_assignments__subject__name__icontains=query)
            | Q(rombel_assignments__study_group__name__icontains=query)
            | Q(rombel_assignments__study_group__school_class__name__icontains=query)
        ).distinct()

    if school_class_id:
        teachers = teachers.filter(rombel_assignments__study_group__school_class_id=school_class_id)

    teachers = teachers.distinct()
    teachers = teachers.order_by("user__full_name")

    grouped_rows = []
    for teacher in teachers:
        assignments = list(
            teacher.rombel_assignments.select_related("study_group__academic_year", "study_group__school_class", "subject")
            .filter(is_active=True)
            .order_by(
                "study_group__academic_year__start_date",
                "study_group__school_class__level_order",
                "study_group__name",
                "subject__sort_order",
                "subject__name",
            )
        )
        if not assignments:
            continue

        assignment_rows = []
        for assignment in assignments:
            assignment_rows.append(
                {
                    "study_group_name": assignment.study_group.name,
                    "school_class_name": assignment.study_group.school_class.name,
                    "academic_year_name": assignment.study_group.academic_year.name,
                    "subject_name": assignment.subject.name,
                    "weekly_hours": assignment.weekly_hours,
                    "minimum_score": assignment.minimum_score,
                    "teacher_name": teacher.user.full_name,
                }
            )

        grouped_rows.append(
            {
                "teacher": teacher,
                "rows": assignment_rows,
                "assignment_count": len(assignment_rows),
                "total_weekly_hours": sum(row["weekly_hours"] for row in assignment_rows),
            }
        )

    context = {
        "query": query,
        "school_classes": SchoolClass.objects.filter(is_active=True).order_by("level_order", "name"),
        "selected_class": school_class_id,
        "grouped_rows": grouped_rows,
        "teacher_count": len(grouped_rows),
        "assignment_count": sum(group["assignment_count"] for group in grouped_rows),
        "total_weekly_hours": sum(group["total_weekly_hours"] for group in grouped_rows),
    }
    return render(request, "academics/curriculum_teacher_hours.html", context)


@login_required
def ledger_list(request):
    query = request.GET.get("q", "").strip()
    grade_books = GradeBook.objects.select_related(
        "academic_year",
        "study_group",
        "study_group__school_class",
        "class_subject",
        "class_subject__subject",
        "class_subject__teacher__user",
    ).annotate(
        total_students=Count("student_grades", distinct=True),
        complete_students=Count(
            "student_grades",
            filter=Q(
                student_grades__knowledge_score__isnull=False,
                student_grades__skill_score__isnull=False,
                student_grades__attitude__gt="",
            ),
            distinct=True,
        ),
    )

    if query:
        grade_books = grade_books.filter(
            Q(study_group__name__icontains=query)
            | Q(study_group__school_class__name__icontains=query)
            | Q(class_subject__subject__name__icontains=query)
            | Q(academic_year__name__icontains=query)
        )

    context = {
        "query": query,
        "grade_books": grade_books,
        "ledger_count": GradeBook.objects.count(),
        "draft_count": GradeBook.objects.filter(status=GradeBook.Status.DRAFT).count(),
        "locked_count": GradeBook.objects.filter(status=GradeBook.Status.LOCKED).count(),
    }
    return render(request, "academics/ledger_list.html", context)


@login_required
def ledger_create(request):
    form = GradeBookForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            grade_book = form.save(commit=False)
            grade_book.created_by = request.user
            grade_book.save()
            _sync_grade_book_students(grade_book)
        messages.success(request, "Ledger nilai berhasil dibuat.")
        return redirect("academics:ledger_detail", pk=grade_book.pk)

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Ledger Nilai",
            "page_title": "Buat ledger nilai",
            "page_description": "Pilih rombel, semester, dan mata pelajaran yang akan dinilai.",
            "submit_label": "Buat ledger",
            "cancel_url": "academics:ledger_list",
        },
    )


@login_required
def ledger_detail(request, pk):
    grade_book = get_object_or_404(
        GradeBook.objects.select_related(
            "academic_year",
            "study_group",
            "study_group__school_class",
            "class_subject",
            "class_subject__subject",
            "class_subject__teacher__user",
        ),
        pk=pk,
    )
    _sync_grade_book_students(grade_book)
    errors = []

    if request.method == "POST":
        if grade_book.status == GradeBook.Status.LOCKED:
            errors.append("Ledger nilai sudah dikunci dan tidak bisa diubah.")
        else:
            grades = grade_book.student_grades.select_related("student__user")
            valid_attitudes = {choice[0] for choice in StudentGrade.Attitude.choices}
            for grade in grades:
                try:
                    knowledge_score = _parse_score(request.POST.get(f"knowledge_{grade.pk}", ""))
                    skill_score = _parse_score(request.POST.get(f"skill_{grade.pk}", ""))
                except ValueError as exc:
                    errors.append(f"{grade.student.user.full_name}: {exc}")
                    continue

                attitude = request.POST.get(f"attitude_{grade.pk}", "").strip()
                if attitude and attitude not in valid_attitudes:
                    errors.append(f"{grade.student.user.full_name}: predikat sikap tidak valid.")
                    continue

                grade.knowledge_score = knowledge_score
                grade.skill_score = skill_score
                grade.attitude = attitude
                grade.teacher_notes = request.POST.get(f"notes_{grade.pk}", "").strip()
                grade.save(update_fields=["knowledge_score", "skill_score", "attitude", "teacher_notes", "updated_at"])

            if not errors:
                if request.POST.get("action") == "lock":
                    incomplete_count = grade_book.student_grades.filter(
                        Q(knowledge_score__isnull=True) | Q(skill_score__isnull=True) | Q(attitude="")
                    ).count()
                    if incomplete_count:
                        errors.append("Ledger belum bisa dikunci karena masih ada nilai yang belum lengkap.")
                    else:
                        grade_book.status = GradeBook.Status.LOCKED
                        grade_book.save(update_fields=["status", "updated_at"])
                        messages.success(request, "Ledger nilai berhasil disimpan dan dikunci.")
                        return redirect("academics:ledger_detail", pk=grade_book.pk)
                else:
                    messages.success(request, "Ledger nilai berhasil disimpan.")
                    return redirect("academics:ledger_detail", pk=grade_book.pk)

    grades = list(grade_book.student_grades.select_related("student__user").order_by("student__user__full_name"))
    complete_count = sum(1 for grade in grades if grade.is_complete)
    below_minimum_count = sum(1 for grade in grades if grade.final_score is not None and not grade.passed_minimum)
    context = {
        "grade_book": grade_book,
        "grades": grades,
        "attitude_choices": StudentGrade.Attitude.choices,
        "complete_count": complete_count,
        "below_minimum_count": below_minimum_count,
        "errors": errors,
    }
    return render(request, "academics/ledger_detail.html", context)


@login_required
def group_report(request, pk):
    study_group = get_object_or_404(
        StudyGroup.objects.select_related("academic_year", "school_class", "homeroom_teacher__user"),
        pk=pk,
    )
    semester = request.GET.get("semester", GradeBook.Semester.ODD)
    if semester not in {choice[0] for choice in GradeBook.Semester.choices}:
        semester = GradeBook.Semester.ODD

    class_subjects, rows = _report_rows(study_group, semester)
    context = {
        "study_group": study_group,
        "semester": semester,
        "semester_choices": GradeBook.Semester.choices,
        "class_subjects": class_subjects,
        "rows": rows,
    }
    return render(request, "academics/group_report.html", context)


@login_required
def year_list(request):
    years = AcademicYear.objects.prefetch_related(
        Prefetch(
            "study_groups",
            queryset=StudyGroup.objects.select_related(
                "school_class",
                "homeroom_teacher__user",
            ).prefetch_related("students__user"),
        )
    ).annotate(
        study_group_total=Count("study_groups", distinct=True),
        source_promotion_run_total=Count("promotion_runs_as_source", distinct=True),
        target_promotion_run_total=Count("promotion_runs_as_target", distinct=True),
    )
    context = {
        "years": years,
        "year_count": AcademicYear.objects.count(),
        "active_year_count": AcademicYear.objects.filter(is_active=True).count(),
        "study_group_count": StudyGroup.objects.count(),
    }
    return render(request, "academics/year_list.html", context)


@login_required
def academic_year_create(request):
    form = AcademicYearCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            academic_year = form.save()
            clone_result = None
            if form.cleaned_data.get("clone_study_groups"):
                clone_result = _clone_study_groups_from_previous_year(academic_year)

        if clone_result:
            if clone_result["source_year"] and clone_result["created"]:
                messages.success(
                    request,
                    (
                        f"Tahun ajaran berhasil ditambahkan. "
                        f"{clone_result['created']} rombel berhasil disalin dari {clone_result['source_year'].name}."
                    ),
                )
            elif clone_result["source_year"]:
                messages.success(
                    request,
                    (
                        "Tahun ajaran berhasil ditambahkan. "
                        f"Tidak ada rombel baru yang bisa disalin dari {clone_result['source_year'].name}."
                    ),
                )
            else:
                messages.success(
                    request,
                    "Tahun ajaran berhasil ditambahkan. Belum ada tahun ajaran sebelumnya untuk disalin.",
                )
        else:
            messages.success(request, "Tahun ajaran berhasil ditambahkan.")
        return redirect("academics:year_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": "Tambah tahun ajaran",
            "page_description": "Tentukan periode belajar dan tandai tahun ajaran aktif bila diperlukan.",
            "submit_label": "Simpan tahun ajaran",
            "cancel_url": "academics:year_list",
            "checkbox_fields": ["is_active", "clone_study_groups"],
        },
    )


@login_required
def academic_year_update(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = AcademicYearForm(request.POST or None, instance=academic_year)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tahun ajaran berhasil diperbarui.")
        return redirect("academics:year_list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": f"Edit tahun ajaran {academic_year.name}",
            "page_description": "Perbarui periode atau status aktif tahun ajaran ini.",
            "submit_label": "Update tahun ajaran",
            "cancel_url": "academics:year_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def academic_year_delete(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    if academic_year.is_active:
        messages.error(request, "Tahun ajaran aktif tidak bisa dihapus. Nonaktifkan dulu tahun ajaran lain sebagai pengganti.")
        return redirect("academics:year_list")

    has_study_groups = academic_year.study_groups.exists()
    has_promotion_runs = academic_year.promotion_runs_as_source.exists() or academic_year.promotion_runs_as_target.exists()
    if has_study_groups or has_promotion_runs:
        reasons = []
        if has_study_groups:
            reasons.append("masih memiliki rombel")
        if has_promotion_runs:
            reasons.append("masih dipakai oleh proses kenaikan kelas")
        messages.error(request, f"Tahun ajaran tidak bisa dihapus karena {', '.join(reasons)}.")
        return redirect("academics:year_list")

    if request.method == "POST":
        try:
            academic_year.delete()
        except ProtectedError:
            messages.error(request, "Tahun ajaran tidak bisa dihapus karena masih dipakai data lain di sistem.")
        else:
            messages.success(request, "Tahun ajaran berhasil dihapus.")
        return redirect("academics:year_list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": academic_year.name,
            "item_type": "tahun ajaran",
            "cancel_url": "academics:year_list",
        },
    )


@login_required
def school_class_create(request):
    form = SchoolClassForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Kelas berhasil ditambahkan.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": "Tambah kelas",
            "page_description": "Masukkan jenjang atau tingkat kelas yang dipakai di madrasah.",
            "submit_label": "Simpan kelas",
            "cancel_url": "academics:overview",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def school_class_update(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    form = SchoolClassForm(request.POST or None, instance=school_class)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Kelas berhasil diperbarui.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": f"Edit kelas {school_class.name}",
            "page_description": "Perbarui nama, urutan, atau deskripsi kelas.",
            "submit_label": "Update kelas",
            "cancel_url": "academics:overview",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def school_class_delete(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    if school_class.study_groups.exists():
        messages.error(request, "Kelas tidak bisa dihapus karena masih dipakai oleh rombel.")
        return redirect("academics:overview")

    if request.method == "POST":
        school_class.delete()
        messages.success(request, "Kelas berhasil dihapus.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": school_class.name,
            "item_type": "kelas",
            "cancel_url": "academics:overview",
        },
    )


@login_required
def study_group_create(request):
    form = StudyGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rombel berhasil ditambahkan.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": "Tambah rombel",
            "page_description": "Hubungkan rombel dengan kelas, tahun ajaran, dan wali kelas.",
            "submit_label": "Simpan rombel",
            "cancel_url": "academics:overview",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def study_group_update(request, pk):
    study_group = get_object_or_404(StudyGroup, pk=pk)
    form = StudyGroupForm(request.POST or None, instance=study_group)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rombel berhasil diperbarui.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Akademik",
            "page_title": f"Edit rombel {study_group.name}",
            "page_description": "Perbarui detail rombel, kapasitas, atau wali kelas.",
            "submit_label": "Update rombel",
            "cancel_url": "academics:overview",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def study_group_delete(request, pk):
    study_group = get_object_or_404(StudyGroup, pk=pk)
    blockers = []
    if study_group.grade_books.exists():
        blockers.append("Ledger nilai masih terhubung ke rombel ini.")
    if study_group.promotion_items_as_source.exists() or study_group.promotion_items_as_target.exists():
        blockers.append("Data kenaikan kelas masih memakai rombel ini sebagai asal atau tujuan.")
    if study_group.students.exists():
        blockers.append("Masih ada siswa yang terhubung ke rombel ini.")

    if request.method == "POST":
        if blockers:
            messages.error(request, "Rombel tidak bisa dihapus karena masih dipakai data lain di sistem.")
            return redirect("academics:overview")
        try:
            study_group.delete()
        except ProtectedError:
            messages.error(
                request,
                "Rombel tidak bisa dihapus karena masih dipakai data akademik lain seperti ledger nilai atau riwayat kenaikan kelas.",
            )
        else:
            messages.success(request, "Rombel berhasil dihapus.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": study_group.name,
            "item_type": "rombel",
            "cancel_url": "academics:overview",
            "delete_warnings": blockers,
        },
    )
