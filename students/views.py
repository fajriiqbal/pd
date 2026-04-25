import re
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import CustomUser
from accounts.audit import record_activity
from academics.models import AcademicYear, GradeBook, SchoolClass, StudyGroup
from teachers.models import TeacherProfile

from .backup_utils import build_backup_archive, restore_backup_archive
from .forms import PromotionStartForm, StudentAlumniDocumentForm, StudentAlumniValidationForm
from .forms import BackupRestoreUploadForm, StudentDocumentForm, StudentImportUploadForm, StudentMutationRecordForm, StudentRecordForm
from .import_utils import (
    build_student_import_preview,
    delete_import_preview,
    execute_student_import,
    load_import_preview,
    save_import_preview,
)
from .models import (
    PromotionRun,
    PromotionRunItem,
    StudentDocument,
    StudentAlumniArchive,
    StudentAlumniDocument,
    StudentAlumniValidation,
    StudentMutationRecord,
    StudentEnrollment,
    StudentProfile,
)


def _can_manage_student(user, student):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role == CustomUser.Role.ADMIN:
        return True
    if user.role == CustomUser.Role.TEACHER and hasattr(user, "teacher_profile"):
        return bool(
            student.study_group_id
            and student.study_group.homeroom_teacher_id == user.teacher_profile.id
        )
    if user.role == CustomUser.Role.STUDENT and hasattr(user, "student_profile"):
        return student.user_id == user.id
    return False


def _is_admin_user(user):
    return user.is_authenticated and (user.is_superuser or user.role == CustomUser.Role.ADMIN)


def _backup_restore_context(form=None):
    return {
        "form": form or BackupRestoreUploadForm(),
        "page_kicker": "Backup Data",
        "page_title": "Backup & restore data",
        "page_description": "Unduh snapshot seluruh data aplikasi dalam format ZIP, lalu pulihkan kapan saja dari menu yang sama.",
        "student_count": StudentProfile.objects.count(),
        "teacher_count": TeacherProfile.objects.count(),
        "academic_year_count": AcademicYear.objects.count(),
        "school_class_count": SchoolClass.objects.count(),
        "study_group_count": StudyGroup.objects.count(),
        "student_document_count": StudentDocument.objects.count(),
        "alumni_count": StudentAlumniArchive.objects.count(),
    }


@login_required
def backup_restore(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied

    if request.method == "POST" and request.POST.get("action") == "download":
        archive_bytes, manifest = build_backup_archive()
        response = HttpResponse(archive_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{manifest["backup_file"]}"'
        return response

    if request.method == "POST" and request.POST.get("action") == "restore":
        form = BackupRestoreUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                result = restore_backup_archive(form.cleaned_data["backup_file"])
            except Exception as exc:  # pragma: no cover - defensive guard for operator-facing action
                messages.error(request, f"Restore gagal: {exc}")
            else:
                messages.success(
                    request,
                    f"Restore selesai. {result['restored_media_count']} file media berhasil dipulihkan.",
                )
                return redirect("students:backup_restore")
        return render(request, "students/backup_restore.html", _backup_restore_context(form))

    return render(request, "students/backup_restore.html", _backup_restore_context())


def _source_students_for_promotion(promotion_run):
    students = StudentProfile.objects.select_related(
        "user",
        "study_group",
        "study_group__academic_year",
        "study_group__school_class",
    ).filter(
        study_group__academic_year=promotion_run.source_academic_year,
        is_active=True,
    )
    if promotion_run.source_school_class_id:
        students = students.filter(study_group__school_class=promotion_run.source_school_class)
    if promotion_run.source_study_group_id:
        students = students.filter(study_group=promotion_run.source_study_group)
    return students.order_by("study_group__school_class__level_order", "study_group__name", "user__full_name")


def _group_suffix(group_name):
    match = re.search(r"([A-Za-z]+)$", group_name.strip())
    return match.group(1).upper() if match else ""


def _next_school_class(source_class):
    return SchoolClass.objects.filter(
        level_order__gt=source_class.level_order,
        is_active=True,
    ).order_by("level_order", "name").first()


def _is_terminal_school_class(source_class):
    return _next_school_class(source_class) is None


def _suggest_target_study_group(source_group, target_academic_year, target_school_class):
    if not target_school_class:
        return None

    target_groups = StudyGroup.objects.filter(
        academic_year=target_academic_year,
        school_class=target_school_class,
        is_active=True,
    ).order_by("name")
    suffix = _group_suffix(source_group.name)
    if suffix:
        suffix_match = [group for group in target_groups if _group_suffix(group.name) == suffix]
        if suffix_match:
            return suffix_match[0]
    return target_groups.first()


def _create_promotion_items(promotion_run):
    action_counts = Counter()
    students = _source_students_for_promotion(promotion_run)

    for student in students:
        source_group = student.study_group
        target_class = _next_school_class(source_group.school_class)
        if target_class:
            action = PromotionRunItem.Action.PROMOTE
            target_group = _suggest_target_study_group(source_group, promotion_run.target_academic_year, target_class)
        else:
            action = PromotionRunItem.Action.GRADUATE
            target_group = None

        PromotionRunItem.objects.create(
            promotion_run=promotion_run,
            student=student,
            source_study_group=source_group,
            target_study_group=target_group,
            action=action,
        )
        action_counts[action] += 1

    return action_counts


def _promotion_summary(items):
    action_counts = Counter(item.action for item in items)
    return {
        "total": sum(action_counts.values()),
        "promote": action_counts.get(PromotionRunItem.Action.PROMOTE, 0),
        "repeat": action_counts.get(PromotionRunItem.Action.REPEAT, 0),
        "graduate": action_counts.get(PromotionRunItem.Action.GRADUATE, 0),
        "transfer": action_counts.get(PromotionRunItem.Action.TRANSFER, 0),
        "inactive": action_counts.get(PromotionRunItem.Action.INACTIVE, 0),
    }


def _update_promotion_items_from_post(promotion_run, post_data):
    errors = []
    valid_actions = {choice[0] for choice in PromotionRunItem.Action.choices}
    target_groups = {
        str(group.pk): group
        for group in StudyGroup.objects.filter(academic_year=promotion_run.target_academic_year)
    }

    items = promotion_run.items.select_related("student__user", "target_study_group")
    for item in items:
        action = post_data.get(f"action_{item.pk}", item.action)
        target_group_id = post_data.get(f"target_group_{item.pk}", "").strip()
        notes = post_data.get(f"notes_{item.pk}", "").strip()

        if action not in valid_actions:
            errors.append(f"{item.student.user.full_name}: aksi kenaikan tidak valid.")
            continue

        target_group = target_groups.get(target_group_id) if target_group_id else None
        if action in {PromotionRunItem.Action.PROMOTE, PromotionRunItem.Action.REPEAT} and not target_group:
            errors.append(f"{item.student.user.full_name}: rombel tujuan wajib diisi.")

        item.action = action
        item.target_study_group = target_group if action in {PromotionRunItem.Action.PROMOTE, PromotionRunItem.Action.REPEAT} else None
        item.notes = notes
        item.save(update_fields=["action", "target_study_group", "notes", "updated_at"])

    return errors


def _promotion_capacity_warnings(promotion_run):
    target_counts = Counter(
        promotion_run.items.filter(
            action__in=[PromotionRunItem.Action.PROMOTE, PromotionRunItem.Action.REPEAT],
            target_study_group__isnull=False,
        ).values_list("target_study_group_id", flat=True)
    )
    if not target_counts:
        return []

    target_groups = StudyGroup.objects.filter(pk__in=target_counts.keys()).annotate(
        existing_students=Count("students", filter=Q(students__is_active=True), distinct=True),
    )
    warnings = []
    for group in target_groups:
        projected_count = group.existing_students + target_counts[group.pk]
        if projected_count > group.capacity:
            warnings.append(
                f"{group.name}: proyeksi {projected_count} siswa melebihi kapasitas {group.capacity}."
            )
    return warnings


def _promotion_execution_errors(promotion_run):
    errors = []
    if promotion_run.status != PromotionRun.Status.DRAFT:
        errors.append("Proses kenaikan ini sudah pernah dijalankan.")

    items = promotion_run.items.select_related("student__user", "target_study_group")
    if not items.exists():
        errors.append("Tidak ada siswa yang bisa diproses.")

    same_year_target = promotion_run.source_academic_year_id == promotion_run.target_academic_year_id
    target_enrollment_student_ids = set()
    if not same_year_target:
        target_enrollment_student_ids = set(
            StudentEnrollment.objects.filter(
                academic_year=promotion_run.target_academic_year,
                student__in=items.values("student"),
            ).values_list("student_id", flat=True)
        )

    for item in items:
        if item.student_id in target_enrollment_student_ids:
            errors.append(f"{item.student.user.full_name}: sudah punya riwayat pada tahun ajaran tujuan.")
        if item.action in {PromotionRunItem.Action.PROMOTE, PromotionRunItem.Action.REPEAT} and not item.target_study_group_id:
            errors.append(f"{item.student.user.full_name}: rombel tujuan wajib diisi.")
        if same_year_target and item.action != PromotionRunItem.Action.GRADUATE:
            errors.append(f"{item.student.user.full_name}: tahun ajaran yang sama hanya boleh untuk kelulusan kelas terminal.")

    return errors


def _promotion_detail_context(promotion_run, errors=None):
    items = promotion_run.items.select_related(
        "student__user",
        "source_study_group",
        "source_study_group__school_class",
        "target_study_group",
        "target_study_group__school_class",
    ).order_by("source_study_group__school_class__level_order", "source_study_group__name", "student__user__full_name")
    target_group_options = StudyGroup.objects.filter(
        academic_year=promotion_run.target_academic_year,
        is_active=True,
    ).select_related("school_class").order_by("school_class__level_order", "name")
    item_list = list(items)
    return {
        "promotion_run": promotion_run,
        "items": item_list,
        "target_group_options": target_group_options,
        "action_choices": PromotionRunItem.Action.choices,
        "summary": _promotion_summary(item_list),
        "capacity_warnings": _promotion_capacity_warnings(promotion_run),
        "errors": errors or [],
        "page_kicker": "Kenaikan Kelas",
        "page_title": "Preview kenaikan kelas",
        "page_description": "Periksa dan sesuaikan keputusan per siswa sebelum proses kenaikan kelas dijalankan.",
    }


def _execute_promotion_run(promotion_run):
    items = promotion_run.items.select_related("student", "target_study_group", "source_study_group")
    summary = _promotion_summary(list(items))
    same_year_target = promotion_run.source_academic_year_id == promotion_run.target_academic_year_id
    status_mapping = {
        PromotionRunItem.Action.PROMOTE: StudentEnrollment.Status.ACTIVE,
        PromotionRunItem.Action.REPEAT: StudentEnrollment.Status.REPEATED,
        PromotionRunItem.Action.GRADUATE: StudentEnrollment.Status.GRADUATED,
        PromotionRunItem.Action.TRANSFER: StudentEnrollment.Status.TRANSFERRED,
        PromotionRunItem.Action.INACTIVE: StudentEnrollment.Status.INACTIVE,
    }

    with transaction.atomic():
        locked_run = PromotionRun.objects.select_for_update().get(pk=promotion_run.pk)
        for item in items:
            source_enrollment, _ = StudentEnrollment.objects.get_or_create(
                student=item.student,
                academic_year=locked_run.source_academic_year,
                defaults={
                    "study_group": item.source_study_group,
                    "status": StudentEnrollment.Status.ACTIVE,
                },
            )
            target_group = item.target_study_group
            final_class_name = item.source_study_group.name if item.source_study_group else item.student.class_name

            if item.action == PromotionRunItem.Action.GRADUATE and same_year_target:
                source_enrollment.study_group = item.source_study_group
                source_enrollment.status = StudentEnrollment.Status.GRADUATED
                source_enrollment.notes = item.notes
                source_enrollment.save(update_fields=["study_group", "status", "notes", "updated_at"])
            else:
                StudentEnrollment.objects.create(
                    student=item.student,
                    academic_year=locked_run.target_academic_year,
                    study_group=target_group,
                    status=status_mapping[item.action],
                    previous_enrollment=source_enrollment,
                    notes=item.notes,
                )

            student = item.student
            if item.action in {PromotionRunItem.Action.PROMOTE, PromotionRunItem.Action.REPEAT}:
                student.study_group = target_group
                student.class_name = target_group.name
                student.is_active = True
            else:
                student.study_group = None
                student.class_name = item.get_action_display()
                student.is_active = False
            student.save(update_fields=["study_group", "class_name", "is_active", "updated_at"])

            if item.action == PromotionRunItem.Action.GRADUATE:
                _sync_student_alumni_archive(student, promotion_run, item.notes, final_class_name)

        locked_run.status = PromotionRun.Status.EXECUTED
        locked_run.executed_at = timezone.now()
        locked_run.summary = summary
        locked_run.save(update_fields=["status", "executed_at", "summary", "updated_at"])


def _sync_student_alumni_archive(
    student,
    promotion_run,
    notes="",
    final_class_name="",
    graduation_status=StudentAlumniArchive.GraduationStatus.GRADUATED,
):
    archive, _ = StudentAlumniArchive.objects.get_or_create(student=student)
    archive.full_name = student.user.full_name
    archive.nis = student.nis or ""
    archive.nisn = student.nisn or ""
    archive.gender = student.gender
    archive.birth_place = student.birth_place
    archive.birth_date = student.birth_date
    archive.address = student.address
    archive.father_name = student.father_name
    archive.father_nik = student.father_nik
    archive.father_birth_place = student.father_birth_place
    archive.father_birth_date = student.father_birth_date
    archive.father_education = student.father_education
    archive.father_job = student.father_job
    archive.mother_name = student.mother_name
    archive.mother_nik = student.mother_nik
    archive.mother_birth_place = student.mother_birth_place
    archive.mother_birth_date = student.mother_birth_date
    archive.mother_education = student.mother_education
    archive.mother_job = student.mother_job
    archive.guardian_name = student.guardian_name
    archive.family_status = student.family_status
    archive.special_needs = student.special_needs
    archive.disability_notes = student.disability_notes
    archive.kip_number = student.kip_number
    archive.class_name = final_class_name or student.class_name
    archive.entry_year = student.entry_year
    archive.graduation_year = promotion_run.target_academic_year.end_date.year if promotion_run.target_academic_year and promotion_run.target_academic_year.end_date else None
    archive.graduation_status = graduation_status
    archive.graduation_notes = notes or ""
    archive.save()


@login_required
def student_mutation_list(request):
    query = request.GET.get("q", "").strip()
    direction = request.GET.get("direction", "").strip()
    mutations = StudentMutationRecord.objects.select_related(
        "student__user",
        "origin_study_group__school_class",
        "destination_study_group__school_class",
        "created_by",
    ).order_by("-mutation_date", "-created_at")

    if query:
        mutations = mutations.filter(
            Q(student__user__full_name__icontains=query)
            | Q(student__nis__icontains=query)
            | Q(student__nisn__icontains=query)
            | Q(origin_school_name__icontains=query)
            | Q(destination_school_name__icontains=query)
        )

    if direction in {StudentMutationRecord.Direction.INBOUND, StudentMutationRecord.Direction.OUTBOUND}:
        mutations = mutations.filter(direction=direction)

    context = {
        "mutations": mutations,
        "query": query,
        "direction": direction,
        "inbound_count": StudentMutationRecord.objects.filter(direction=StudentMutationRecord.Direction.INBOUND).count(),
        "outbound_count": StudentMutationRecord.objects.filter(direction=StudentMutationRecord.Direction.OUTBOUND).count(),
    }
    return render(request, "students/mutation_list.html", context)


@login_required
def student_mutation_create(request):
    form = StudentMutationRecordForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        mutation = form.save(commit=False)
        mutation.created_by = request.user
        mutation.save()

        student = mutation.student
        if mutation.direction == StudentMutationRecord.Direction.INBOUND:
            if mutation.destination_study_group_id:
                student.study_group = mutation.destination_study_group
                student.class_name = mutation.destination_study_group.name
            student.is_active = True
            student.save(update_fields=["study_group", "class_name", "is_active", "updated_at"])
        else:
            student.is_active = False
            student.study_group = None
            student.save(update_fields=["study_group", "is_active", "updated_at"])
            final_class_name = student.class_name
            _sync_student_alumni_archive(
                student,
                promotion_run=type(
                    "_MutationRun",
                    (),
                    {
                        "target_academic_year": None,
                    },
                )(),
                notes=mutation.notes or mutation.reason,
                final_class_name=final_class_name,
                graduation_status=StudentAlumniArchive.GraduationStatus.TRANSFERRED,
            )

        messages.success(request, "Data mutasi siswa berhasil disimpan.")
        return redirect("students:detail", pk=student.pk)

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Mutasi Siswa",
            "page_title": "Tambah mutasi siswa",
            "page_description": "Catat mutasi masuk atau keluar lengkap dengan sekolah asal/tujuan dan rombel terkait.",
            "submit_label": "Simpan mutasi",
            "cancel_url": "students:list",
            "checkbox_fields": [],
        },
    )


@login_required
def student_list(request):
    if not (request.user.is_superuser or request.user.role == CustomUser.Role.ADMIN):
        raise PermissionDenied

    query = request.GET.get("q", "").strip()
    class_id = request.GET.get("class", "").strip()
    study_group_id = request.GET.get("study_group", "").strip()
    status = request.GET.get("status", "").strip()
    nis_status = request.GET.get("nis_status", "").strip()
    students = StudentProfile.objects.select_related("user", "study_group", "study_group__school_class").all()

    if query:
        students = students.filter(
            Q(user__full_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(nis__icontains=query)
            | Q(nisn__icontains=query)
            | Q(class_name__icontains=query)
            | Q(study_group__name__icontains=query)
            | Q(study_group__school_class__name__icontains=query)
        )

    if class_id and study_group_id:
        matching_group_exists = StudyGroup.objects.filter(
            pk=study_group_id,
            school_class_id=class_id,
        ).exists()
        if not matching_group_exists:
            study_group_id = ""

    if class_id:
        students = students.filter(study_group__school_class_id=class_id)

    if study_group_id:
        students = students.filter(study_group_id=study_group_id)

    if status == "active":
        students = students.filter(is_active=True)
    elif status == "inactive":
        students = students.filter(is_active=False)

    if nis_status == "filled":
        students = students.filter(nis__isnull=False).exclude(nis="")
    elif nis_status == "missing":
        students = students.filter(Q(nis__isnull=True) | Q(nis=""))

    class_options = SchoolClass.objects.filter(
        study_groups__students__isnull=False,
    ).distinct().order_by("level_order", "name")
    study_group_options = StudyGroup.objects.filter(
        students__isnull=False,
    ).select_related("school_class").annotate(
        total_students=Count("students", distinct=True),
    ).distinct().order_by(
        "-academic_year__start_date",
        "school_class__level_order",
        "name",
    )
    import_result = request.session.pop("student_import_result", None)
    context = {
        "students": students,
        "query": query,
        "class_id": class_id,
        "study_group_id": study_group_id,
        "status": status,
        "nis_status": nis_status,
        "class_options": class_options,
        "study_group_options": study_group_options,
        "import_result": import_result,
    }
    return render(request, "students/student_list.html", context)


@login_required
def student_import_preview(request):
    if request.method != "POST":
        return redirect("students:list")

    form = StudentImportUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "File import belum valid. Periksa file dan password default.")
        return redirect("students:list")

    preview_payload = build_student_import_preview(
        form.cleaned_data["excel_file"],
        form.cleaned_data["default_password"],
    )

    if not preview_payload.get("ok"):
        request.session["student_import_result"] = {
            "title": "Preview import gagal",
            "created": 0,
            "updated": 0,
            "failed": len(preview_payload.get("errors", [])),
            "errors": preview_payload.get("errors", []),
        }
        return redirect("students:list")

    token = save_import_preview(preview_payload)
    context = {
        "preview": preview_payload,
        "preview_token": token,
        "page_kicker": "Import Siswa",
        "page_title": "Preview import data siswa",
        "page_description": "Periksa dulu jumlah data baru, data update, kelas/rombel yang akan dibuat, dan baris yang gagal sebelum import dijalankan.",
    }
    return render(request, "students/import_preview.html", context)


@login_required
def student_import_execute(request):
    if request.method != "POST":
        return redirect("students:list")

    token = request.POST.get("preview_token", "").strip()
    preview_payload = load_import_preview(token)
    if not preview_payload:
        messages.error(request, "Data preview import tidak ditemukan atau sudah kedaluwarsa.")
        return redirect("students:list")

    result = execute_student_import(preview_payload)
    delete_import_preview(token)

    request.session["student_import_result"] = {
        "title": "Import siswa selesai",
        "created": result["created"],
        "updated": result["updated"],
        "failed": result["failed"],
        "class_created": result["class_created"],
        "group_created": result["group_created"],
        "errors": result["errors"][:10],
    }
    return redirect("students:list")


@login_required
def student_detail(request, pk):
    student = get_object_or_404(
        StudentProfile.objects.select_related(
            "user",
            "study_group",
            "study_group__academic_year",
            "study_group__school_class",
        ),
        pk=pk,
    )
    if not _can_manage_student(request.user, student):
        raise PermissionDenied
    enrollments = student.enrollments.select_related(
        "academic_year",
        "study_group",
        "study_group__school_class",
        "previous_enrollment",
    ).order_by("-academic_year__start_date")
    grades = student.grades.select_related(
        "grade_book",
        "grade_book__academic_year",
        "grade_book__study_group",
        "grade_book__class_subject",
        "grade_book__class_subject__subject",
        "grade_book__class_subject__teacher__user",
    ).order_by(
        "-grade_book__academic_year__start_date",
        "grade_book__semester",
        "grade_book__class_subject__subject__sort_order",
    )
    grade_list = list(grades)
    complete_grade_count = sum(1 for grade in grade_list if grade.is_complete)
    below_minimum_count = sum(1 for grade in grade_list if grade.final_score is not None and not grade.passed_minimum)
    available_semesters = GradeBook.Semester.choices
    alumni_archive = StudentAlumniArchive.objects.filter(student=student).prefetch_related("documents").first()
    document_count = student.documents.count()

    context = {
        "student": student,
        "enrollments": enrollments,
        "grades": grade_list,
        "complete_grade_count": complete_grade_count,
        "below_minimum_count": below_minimum_count,
        "available_semesters": available_semesters,
        "alumni_archive": alumni_archive,
        "document_count": document_count,
        "can_edit_student": _can_manage_student(request.user, student),
        "page_kicker": "Akademik Siswa",
        "page_title": student.user.full_name,
        "page_description": "Ringkasan rombel aktif, riwayat penempatan, dan nilai raport siswa.",
    }
    return render(request, "students/student_detail.html", context)


@login_required
def alumni_list(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    alumni = StudentAlumniArchive.objects.select_related("student__user").prefetch_related("documents").all()

    if query:
        alumni = alumni.filter(
            Q(full_name__icontains=query)
            | Q(nis__icontains=query)
            | Q(nisn__icontains=query)
            | Q(class_name__icontains=query)
            | Q(student__user__username__icontains=query)
        )

    if status:
        alumni = alumni.filter(graduation_status=status)

    context = {
        "alumni": alumni,
        "query": query,
        "status": status,
    }
    return render(request, "students/alumni_list.html", context)


@login_required
def alumni_detail(request, pk):
    if not _is_admin_user(request.user):
        raise PermissionDenied
    alumni = get_object_or_404(
        StudentAlumniArchive.objects.select_related("student__user"),
        pk=pk,
    )
    document_form = StudentAlumniDocumentForm()
    try:
        validation = alumni.validation
    except StudentAlumniValidation.DoesNotExist:
        validation = None
    validation_form = StudentAlumniValidationForm(instance=validation)
    context = {
        "alumni": alumni,
        "document_form": document_form,
        "validation_form": validation_form,
    }
    return render(request, "students/alumni_detail.html", context)


@login_required
def alumni_document_add(request, pk):
    if not _is_admin_user(request.user):
        raise PermissionDenied
    alumni = get_object_or_404(StudentAlumniArchive, pk=pk)
    form = StudentAlumniDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.alumni = alumni
        document.save()
        messages.success(request, "Dokumen alumni berhasil ditambahkan.")
        return redirect("students:alumni_detail", pk=alumni.pk)

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Alumni",
            "page_title": f"Tambah dokumen {alumni.full_name}",
            "page_description": "Unggah dokumen penting seperti ijazah, rapor, KK, atau akta ke arsip alumni.",
            "submit_label": "Simpan dokumen",
            "cancel_url": "students:alumni_list",
            "checkbox_fields": [],
        },
    )


@login_required
def alumni_document_delete(request, pk, document_pk):
    if not _is_admin_user(request.user):
        raise PermissionDenied
    alumni = get_object_or_404(StudentAlumniArchive, pk=pk)
    document = get_object_or_404(StudentAlumniDocument, pk=document_pk, alumni=alumni)
    if request.method == "POST":
        document.delete()
        messages.success(request, "Dokumen alumni berhasil dihapus.")
        return redirect("students:alumni_detail", pk=alumni.pk)

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": document.title,
            "item_type": "dokumen alumni",
            "cancel_url": "students:alumni_list",
        },
    )


@login_required
def alumni_validation_list(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    alumni = list(
        StudentAlumniArchive.objects.select_related("student__user")
        .prefetch_related("documents")
        .order_by("-graduation_year", "full_name")
    )

    for item in alumni:
        try:
            item.validation_record = item.validation
        except StudentAlumniValidation.DoesNotExist:
            item.validation_record = None

    if query:
        alumni = [
            item
            for item in alumni
            if query.lower() in (item.full_name or "").lower()
            or query.lower() in (item.nis or "").lower()
            or query.lower() in (item.nisn or "").lower()
        ]

    if status:
        alumni = [
            item
            for item in alumni
            if (item.validation_record.status if item.validation_record else StudentAlumniValidation.Status.PENDING) == status
        ]

    def _validation_status(item):
        return item.validation_record.status if item.validation_record else StudentAlumniValidation.Status.PENDING

    alumni.sort(key=lambda item: (item.validation_record is not None, _validation_status(item), item.full_name), reverse=True)

    context = {
        "alumni": alumni,
        "query": query,
        "status": status,
    }
    return render(request, "students/alumni_validation_list.html", context)


@login_required
def alumni_validation_update(request, pk):
    if not _is_admin_user(request.user):
        raise PermissionDenied
    alumni = get_object_or_404(StudentAlumniArchive.objects.select_related("student__user"), pk=pk)
    try:
        validation = alumni.validation
    except StudentAlumniValidation.DoesNotExist:
        validation = None
    form = StudentAlumniValidationForm(request.POST or None, instance=validation)

    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.alumni = alumni
        record.validated_by = request.user
        record.validated_at = timezone.now()
        record.status = record.calculate_status()
        record.save()
        messages.success(request, "Validasi ijazah berhasil disimpan.")
        return redirect("students:alumni_detail", pk=alumni.pk)

    return render(
        request,
        "students/alumni_validation_form.html",
        {
            "form": form,
            "alumni": alumni,
            "page_kicker": "Validasi Alumni",
            "page_title": f"Validasi ijazah {alumni.full_name}",
            "page_description": "Cocokkan nama pada sistem pemerintah, ijazah, KK, dan akta sebelum arsip ditetapkan selesai.",
            "submit_label": "Simpan validasi",
        },
    )


@login_required
def promotion_list(request):
    form = PromotionStartForm()
    promotion_runs = PromotionRun.objects.select_related(
        "source_academic_year",
        "target_academic_year",
        "source_school_class",
        "source_study_group",
        "created_by",
    ).annotate(item_count=Count("items")).order_by("-created_at")[:15]
    return render(
        request,
        "students/promotion_list.html",
        {
            "form": form,
            "promotion_runs": promotion_runs,
            "page_kicker": "Kenaikan Kelas",
            "page_title": "Kenaikan kelas siswa",
            "page_description": "Buat draft kenaikan kelas, cek preview per siswa, lalu jalankan saat data sudah benar.",
        },
    )


@login_required
def promotion_create(request):
    if request.method != "POST":
        return redirect("students:promotion_list")

    form = PromotionStartForm(request.POST)
    if not form.is_valid():
        promotion_runs = PromotionRun.objects.select_related(
            "source_academic_year",
            "target_academic_year",
            "source_school_class",
            "source_study_group",
            "created_by",
        ).annotate(item_count=Count("items")).order_by("-created_at")[:15]
        return render(
            request,
            "students/promotion_list.html",
            {
                "form": form,
                "promotion_runs": promotion_runs,
                "page_kicker": "Kenaikan Kelas",
                "page_title": "Kenaikan kelas siswa",
                "page_description": "Buat draft kenaikan kelas, cek preview per siswa, lalu jalankan saat data sudah benar.",
            },
        )

    with transaction.atomic():
        promotion_run = form.save(commit=False)
        promotion_run.created_by = request.user
        promotion_run.save()
        action_counts = _create_promotion_items(promotion_run)
        total_students = sum(action_counts.values())
        if total_students == 0:
            promotion_run.delete()
            messages.error(request, "Tidak ada siswa aktif yang cocok dengan pilihan tahun, kelas, atau rombel asal.")
            return redirect("students:promotion_list")

        promotion_run.summary = {
            "total": total_students,
            "promote": action_counts.get(PromotionRunItem.Action.PROMOTE, 0),
            "graduate": action_counts.get(PromotionRunItem.Action.GRADUATE, 0),
        }
        promotion_run.save(update_fields=["summary", "updated_at"])

    messages.success(request, "Draft kenaikan kelas berhasil dibuat. Silakan cek preview sebelum dijalankan.")
    return redirect("students:promotion_detail", pk=promotion_run.pk)


@login_required
def promotion_detail(request, pk):
    promotion_run = get_object_or_404(PromotionRun, pk=pk)
    return render(request, "students/promotion_detail.html", _promotion_detail_context(promotion_run))


@login_required
def promotion_execute(request, pk):
    if request.method != "POST":
        return redirect("students:promotion_detail", pk=pk)

    promotion_run = get_object_or_404(PromotionRun, pk=pk)
    update_errors = _update_promotion_items_from_post(promotion_run, request.POST)
    execution_errors = _promotion_execution_errors(promotion_run)
    errors = update_errors + execution_errors
    if errors:
        return render(request, "students/promotion_detail.html", _promotion_detail_context(promotion_run, errors))

    _execute_promotion_run(promotion_run)
    messages.success(request, "Kenaikan kelas berhasil dijalankan dan riwayat siswa sudah tersimpan.")
    return redirect("students:promotion_detail", pk=promotion_run.pk)


@login_required
def promotion_delete(request, pk):
    promotion_run = get_object_or_404(PromotionRun.objects.select_related(
        "source_academic_year",
        "target_academic_year",
    ), pk=pk)

    if request.method != "POST":
        return redirect("students:promotion_list")

    run_label = f"{promotion_run.source_academic_year.name} ke {promotion_run.target_academic_year.name}"
    promotion_run.delete()
    messages.success(request, f"Riwayat kenaikan kelas {run_label} berhasil dihapus.")
    return redirect("students:promotion_list")


@login_required
def student_create(request):
    if not (request.user.is_superuser or request.user.role == CustomUser.Role.ADMIN):
        raise PermissionDenied

    form = StudentRecordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        record_activity(
            request,
            action="create",
            module="Siswa",
            object_label=student.user.full_name,
            object_id=student.pk,
            message="Data siswa baru ditambahkan.",
        )
        messages.success(request, "Data siswa berhasil ditambahkan.")
        return redirect("students:list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Input Siswa",
            "page_title": "Tambah data siswa",
            "page_description": "Lengkapi akun login dan profil siswa dalam satu form operator.",
            "submit_label": "Simpan siswa",
            "cancel_url": "students:list",
            "checkbox_fields": ["is_school_active", "is_active"],
        },
    )


@login_required
def student_update(request, pk):
    student = get_object_or_404(StudentProfile, pk=pk)
    if not _can_manage_student(request.user, student):
        raise PermissionDenied

    active_tab = "data-siswa"
    form = StudentRecordForm(instance=student)
    upload_form = StudentDocumentForm()

    if request.method == "POST":
        form_type = request.POST.get("form_type", "profile")
        if form_type == "profile":
            form = StudentRecordForm(request.POST, instance=student)
            if form.is_valid():
                student = form.save()
                record_activity(
                    request,
                    action="update",
                    module="Siswa",
                    object_label=student.user.full_name,
                    object_id=student.pk,
                    message="Data siswa diperbarui dari menu edit.",
                )
                messages.success(request, "Data siswa berhasil diperbarui.")
                return redirect("students:edit", pk=student.pk)

            if any(field in form.errors for field in ["father_name", "father_nik", "father_birth_place", "father_birth_date", "father_education", "father_job", "mother_name", "mother_nik", "mother_birth_place", "mother_birth_date", "mother_education", "mother_job", "guardian_name", "family_status"]):
                active_tab = "data-orang-tua"
            elif any(field in form.errors for field in ["address", "kip_number", "special_needs", "disability_notes"]):
                active_tab = "data-alamat"
        elif form_type == "upload-berkas":
            upload_form = StudentDocumentForm(request.POST, request.FILES)
            if upload_form.is_valid():
                document = upload_form.save(commit=False)
                document.student = student
                document.save()
                record_activity(
                    request,
                    action="upload",
                    module="Berkas Siswa",
                    object_label=f"{student.user.full_name} - {document.title}",
                    object_id=document.pk,
                    message="Berkas siswa diunggah melalui menu edit.",
                )
                messages.success(request, "Berkas siswa berhasil diunggah.")
                return redirect("students:edit", pk=student.pk)
            active_tab = "upload-berkas"

    return render(
        request,
        "students/student_profile_form.html",
        {
            "student": student,
            "form": form,
            "upload_form": upload_form,
            "documents": student.documents.all(),
            "page_kicker": "Profil Siswa",
            "page_title": f"Edit data siswa {student.user.full_name}",
            "page_description": "Perbarui data siswa, data orang tua, dan alamat dalam tampilan tab yang lebih rapi.",
            "submit_label": "Simpan perubahan",
            "cancel_url": "students:list",
            "checkbox_fields": ["is_school_active", "is_active"],
            "active_tab": active_tab,
        },
    )


@login_required
def student_attachment_delete(request, pk, document_pk):
    student = get_object_or_404(StudentProfile, pk=pk)
    if not _can_manage_student(request.user, student):
        raise PermissionDenied

    document = get_object_or_404(StudentDocument, pk=document_pk, student=student)
    if request.method == "POST":
        document_label = document.title
        document.delete()
        record_activity(
            request,
            action="delete",
            module="Berkas Siswa",
            object_label=f"{student.user.full_name} - {document_label}",
            object_id=document_pk,
            message="Berkas siswa dihapus dari menu edit.",
        )
        messages.success(request, "Berkas siswa berhasil dihapus.")
    return redirect("students:edit", pk=student.pk)


@login_required
def student_delete(request, pk):
    if not (request.user.is_superuser or request.user.role == CustomUser.Role.ADMIN):
        raise PermissionDenied

    student = get_object_or_404(StudentProfile.objects.select_related("user"), pk=pk)
    if request.method == "POST":
        student_name = student.user.full_name
        student_pk = student.pk
        with transaction.atomic():
            student.user.delete()
        record_activity(
            request,
            action="delete",
            module="Siswa",
            object_label=student_name,
            object_id=student_pk,
            message="Data siswa dihapus dari sistem.",
        )
        messages.success(request, "Data siswa berhasil dihapus.")
        return redirect("students:list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": student.user.full_name,
            "item_type": "data siswa",
            "cancel_url": "students:list",
        },
    )


@login_required
def student_bulk_delete(request):
    if not (request.user.is_superuser or request.user.role == CustomUser.Role.ADMIN):
        raise PermissionDenied

    if request.method != "POST":
        return redirect("students:list")

    selected_ids = request.POST.getlist("selected_students")
    if not selected_ids:
        messages.error(request, "Pilih minimal satu siswa yang ingin dihapus.")
        return redirect("students:list")

    students = StudentProfile.objects.select_related("user").filter(pk__in=selected_ids)
    user_ids = list(students.values_list("user_id", flat=True))
    student_logs = [(student.user.full_name, student.pk) for student in students]
    deleted_count = len(user_ids)

    if not deleted_count:
        messages.error(request, "Data siswa yang dipilih tidak ditemukan.")
        return redirect("students:list")

    with transaction.atomic():
        CustomUser.objects.filter(pk__in=user_ids).delete()

    for student_name, student_pk in student_logs:
        record_activity(
            request,
            action="delete",
            module="Siswa",
            object_label=student_name,
            object_id=student_pk,
            message="Data siswa dihapus melalui hapus massal.",
        )

    messages.success(request, f"{deleted_count} data siswa berhasil dihapus.")
    return redirect("students:list")
