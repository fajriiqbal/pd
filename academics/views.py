from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CustomUser
from students.models import StudentProfile

from .curriculum import SUBJECT_PRESETS
from .forms import AcademicYearForm, ClassSubjectForm, GradeBookForm, SchoolClassForm, StudyGroupForm, SubjectForm
from .models import AcademicYear, ClassSubject, GradeBook, SchoolClass, StudentGrade, StudyGroup, Subject


def _sync_grade_book_students(grade_book):
    students = grade_book.study_group.students.filter(is_active=True).select_related("user").order_by("user__full_name")
    for student in students:
        StudentGrade.objects.get_or_create(grade_book=grade_book, student=student)


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
    form = AcademicYearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
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
            "checkbox_fields": ["is_active"],
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
    if academic_year.study_groups.exists():
        messages.error(request, "Tahun ajaran tidak bisa dihapus karena masih memiliki rombel.")
        return redirect("academics:year_list")

    if request.method == "POST":
        academic_year.delete()
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
    if study_group.students.exists():
        messages.error(request, "Rombel tidak bisa dihapus karena masih memiliki siswa terhubung.")
        return redirect("academics:overview")

    if request.method == "POST":
        study_group.delete()
        messages.success(request, "Rombel berhasil dihapus.")
        return redirect("academics:overview")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": study_group.name,
            "item_type": "rombel",
            "cancel_url": "academics:overview",
        },
    )
