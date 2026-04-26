from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone

from accounts.models import ActivityLog
from accounts.models import CustomUser
from academics.models import AcademicYear, ClassSubject, StudyGroup
from students.models import StudentDocument, StudentProfile
from teachers.models import TeacherAdditionalTask, TeacherProfile


def _percent(part, whole):
    if not whole:
        return 0
    return round((part / whole) * 100)


def _build_workflow_steps(active_year, groups_without_homeroom, students_without_group, teachers_without_subject, inactive_accounts):
    return [
        {
            "title": "Tetapkan tahun ajaran aktif",
            "summary": "Pastikan satu tahun ajaran aktif dipakai sebagai acuan seluruh proses semester.",
            "detail": "Tanpa tahun ajaran aktif, rombel, wali kelas, dan ledger akan terasa terpecah.",
            "status": "Wajib di awal",
            "action_label": "Kelola tahun ajaran",
            "url": "/academics/years/add/" if not active_year else "/academics/years/",
            "count": 1 if not active_year else 0,
        },
        {
            "title": "Lengkapi data siswa",
            "summary": "Isi biodata, rombel, dan data wali agar administrasi siswa siap dipakai.",
            "detail": "Data siswa yang rapi akan memudahkan absensi, kenaikan kelas, dan laporan.",
            "status": "Prioritas",
            "action_label": "Buka data siswa",
            "url": "/students/",
            "count": students_without_group.count(),
        },
        {
            "title": "Atur guru, mapel, dan tugas tambahan",
            "summary": "Hubungkan guru dengan mapel pengampu, kelas, serta amanah tambahan.",
            "detail": "Bagian ini penting supaya struktur pengajaran dan monitoring guru konsisten.",
            "status": "Setelah siswa",
            "action_label": "Buka data guru",
            "url": "/teachers/",
            "count": teachers_without_subject.count(),
        },
        {
            "title": "Lengkapi rombel dan wali kelas",
            "summary": "Pastikan setiap rombel sudah memiliki wali kelas dan pengaturan kelas aktif.",
            "detail": "Langkah ini mengikat siswa dan guru ke struktur pembelajaran semester berjalan.",
            "status": "Verifikasi",
            "action_label": "Atur rombel",
            "url": "/academics/",
            "count": groups_without_homeroom.count(),
        },
        {
            "title": "Finalisasi ledger dan cek akun",
            "summary": "Periksa nilai, pastikan akun aktif, lalu siapkan laporan akhir semester.",
            "detail": "Tahap ini menutup siklus kerja operator sebelum pindah ke semester berikutnya.",
            "status": "Penutup",
            "action_label": "Lihat ledger",
            "url": "/academics/ledgers/",
            "count": inactive_accounts.count(),
        },
    ]


def _global_search(query):
    q = (query or "").strip()
    if not q:
        return {
            "query": "",
            "students": [],
            "teachers": [],
            "groups": [],
            "years": [],
        }

    students = (
        StudentProfile.objects.select_related("user", "study_group", "study_group__school_class")
        .filter(
            Q(user__full_name__icontains=q)
            | Q(user__username__icontains=q)
            | Q(nis__icontains=q)
            | Q(nisn__icontains=q)
            | Q(guardian_name__icontains=q)
        )
        .order_by("user__full_name")[:8]
    )
    teachers = (
        TeacherProfile.objects.select_related("user")
        .filter(
            Q(user__full_name__icontains=q)
            | Q(user__username__icontains=q)
            | Q(nip__icontains=q)
        )
        .order_by("user__full_name")[:8]
    )
    groups = (
        StudyGroup.objects.select_related("academic_year", "school_class", "homeroom_teacher__user")
        .filter(
            Q(name__icontains=q)
            | Q(school_class__name__icontains=q)
            | Q(academic_year__name__icontains=q)
        )
        .order_by("-academic_year__start_date", "school_class__level_order", "name")[:8]
    )
    years = AcademicYear.objects.filter(name__icontains=q).order_by("-start_date")[:8]
    return {
        "query": q,
        "students": students,
        "teachers": teachers,
        "groups": groups,
        "years": years,
    }


def _teacher_dashboard_context(user):
    teacher_profile = getattr(user, "teacher_profile", None)
    teaching_assignments = ClassSubject.objects.select_related("school_class", "subject").filter(
        teacher=teacher_profile,
        is_active=True,
    )
    additional_tasks = TeacherAdditionalTask.objects.filter(
        teacher=teacher_profile,
        is_active=True,
    )
    homeroom_groups = StudyGroup.objects.select_related(
        "academic_year",
        "school_class",
    ).filter(
        homeroom_teacher=teacher_profile,
        is_active=True,
    )

    return {
        "dashboard_mode": "teacher",
        "teacher_profile": teacher_profile,
        "teacher_teaching_count": teaching_assignments.count(),
        "teacher_task_count": additional_tasks.count(),
        "teacher_homeroom_count": homeroom_groups.count(),
        "teacher_teaching_assignments": teaching_assignments[:6],
        "teacher_additional_tasks": additional_tasks[:6],
        "teacher_homeroom_groups": homeroom_groups[:6],
        "page_kicker": "Dashboard Guru",
        "page_title": "Ringkasan kerja guru",
        "page_description": "Fokus pada mapel yang diajar, tugas tambahan, dan rombel yang dibimbing.",
    }


def _student_dashboard_context(user):
    student_profile = getattr(user, "student_profile", None)
    documents = student_profile.documents.all().order_by("-uploaded_at") if student_profile else StudentDocument.objects.none()
    return {
        "dashboard_mode": "student",
        "student_profile": student_profile,
        "student_document_count": documents.count(),
        "student_documents": documents[:6],
        "page_kicker": "Dashboard Siswa",
        "page_title": "Ringkasan data siswa",
        "page_description": "Data pribadi dan berkas penting hanya ditampilkan untuk akun yang bersangkutan.",
    }


@login_required
def home(request):
    if request.user.role == CustomUser.Role.TEACHER and hasattr(request.user, "teacher_profile"):
        context = {
            "student_count": 0,
            "teacher_count": 0,
            "account_count": 0,
            "study_group_count": 0,
            "show_login_briefing": False,
            "login_briefing_actions": [],
        }
        context.update(_teacher_dashboard_context(request.user))
        return render(request, "dashboard/home.html", context)

    if request.user.role == CustomUser.Role.STUDENT and hasattr(request.user, "student_profile"):
        context = {
            "student_count": 0,
            "teacher_count": 0,
            "account_count": 0,
            "study_group_count": 0,
            "show_login_briefing": False,
            "login_briefing_actions": [],
        }
        context.update(_student_dashboard_context(request.user))
        return render(request, "dashboard/home.html", context)

    show_login_briefing = bool(request.session.pop("show_login_briefing", False))
    active_year = AcademicYear.objects.filter(is_active=True).first()
    active_students = StudentProfile.objects.filter(is_active=True)
    groups_without_homeroom = StudyGroup.objects.filter(is_active=True, homeroom_teacher__isnull=True)
    students_without_group = active_students.filter(study_group__isnull=True)
    students_without_guardian = active_students.filter(
        Q(guardian_name="") | Q(guardian_name__isnull=True)
    )
    teachers_without_subject = TeacherProfile.objects.filter(is_active=True).filter(
        Q(subject="") | Q(subject__isnull=True)
    )
    inactive_accounts = CustomUser.objects.filter(is_school_active=False)
    orphan_family_statuses = [
        StudentProfile.FamilyStatus.ORPHAN_FATHER,
        StudentProfile.FamilyStatus.ORPHAN_MOTHER,
        StudentProfile.FamilyStatus.ORPHAN_BOTH,
    ]
    kip_number_students = StudentProfile.objects.filter(is_active=True).exclude(kip_number="").exclude(kip_number__isnull=True)
    special_needs_students = StudentProfile.objects.filter(is_active=True).filter(
        Q(special_needs__isnull=False) & ~Q(special_needs="")
    ) | StudentProfile.objects.filter(is_active=True).filter(
        Q(disability_notes__isnull=False) & ~Q(disability_notes="")
    )
    special_needs_students = special_needs_students.distinct()
    parents_missing = StudentProfile.objects.filter(is_active=True).filter(
        Q(father_name="") | Q(father_name__isnull=True) | Q(mother_name="") | Q(mother_name__isnull=True)
    )
    kip_pip_documents = StudentDocument.objects.filter(document_type=StudentDocument.DocumentType.KIP_PIP)
    data_complete_students = active_students.filter(
        nis__isnull=False,
        nisn__isnull=False,
        gender__isnull=False,
    ).exclude(
        nis=""
    ).exclude(
        nisn=""
    )
    parent_complete_students = active_students.filter(
        father_name__isnull=False,
        mother_name__isnull=False,
    ).exclude(
        father_name=""
    ).exclude(
        mother_name=""
    )
    document_complete_students = active_students.filter(documents__isnull=False).distinct()

    active_student_count = active_students.count()
    health_cards = [
        {
            "title": "Identitas inti lengkap",
            "count": data_complete_students.count(),
            "total": active_student_count,
            "percent": _percent(data_complete_students.count(), active_student_count),
            "description": "NIS, NISN, dan gender sudah terisi.",
        },
        {
            "title": "Data orang tua lengkap",
            "count": parent_complete_students.count(),
            "total": active_student_count,
            "percent": _percent(parent_complete_students.count(), active_student_count),
            "description": "Ayah dan ibu sudah tercatat pada profil siswa.",
        },
        {
            "title": "Punya KIP/PIP",
            "count": kip_number_students.count(),
            "total": active_student_count,
            "percent": _percent(kip_number_students.count(), active_student_count),
            "description": "Nomor KIP/PIP sudah diisi pada siswa aktif.",
        },
        {
            "title": "Berkas tersimpan",
            "count": document_complete_students.count(),
            "total": active_student_count,
            "percent": _percent(document_complete_students.count(), active_student_count),
            "description": "Minimal satu berkas sudah diunggah di menu edit siswa.",
        },
    ]

    alert_cards = [
        {
            "title": "Siswa tanpa rombel",
            "count": students_without_group.count(),
            "severity": "high" if students_without_group.exists() else "ok",
            "description": "Masukkan ke rombel aktif agar administrasi berjalan.",
        },
        {
            "title": "Data orang tua belum lengkap",
            "count": parents_missing.count(),
            "severity": "medium" if parents_missing.exists() else "ok",
            "description": "Lengkapi ayah atau ibu untuk arsip keluarga.",
        },
        {
            "title": "Belum ada berkas KIP/PIP",
            "count": max(kip_number_students.count() - kip_pip_documents.count(), 0),
            "severity": "medium" if kip_number_students.count() > kip_pip_documents.count() else "ok",
            "description": "Upload kartu KIP/PIP di menu edit siswa.",
        },
        {
            "title": "Data tanpa wali kelas",
            "count": groups_without_homeroom.count(),
            "severity": "high" if groups_without_homeroom.exists() else "ok",
            "description": "Tentukan guru wali kelas untuk rombel aktif.",
        },
    ]

    active_year_groups = StudyGroup.objects.none()
    if active_year:
        active_year_groups = (
            StudyGroup.objects.filter(academic_year=active_year, is_active=True)
            .select_related("school_class", "homeroom_teacher__user")
            .annotate(active_student_count=Count("students", filter=Q(students__is_active=True), distinct=True))
            .order_by("school_class__level_order", "name")
        )

    completion_cards = [
        {
            "title": "Rombel tanpa wali kelas",
            "count": groups_without_homeroom.count(),
            "description": "Tentukan guru wali agar struktur akademik siap dipakai modul absensi dan nilai.",
            "url": "/academics/",
            "action_label": "Lengkapi rombel",
        },
        {
            "title": "Siswa belum masuk rombel",
            "count": students_without_group.count(),
            "description": "Hubungkan siswa ke rombel aktif supaya data kelas lebih akurat.",
            "url": "/students/",
            "action_label": "Atur siswa",
        },
        {
            "title": "Guru belum punya mapel",
            "count": teachers_without_subject.count(),
            "description": "Isi mapel guru untuk mempermudah jadwal, wali, dan laporan.",
            "url": "/teachers/",
            "action_label": "Periksa guru",
        },
        {
            "title": "Akun sekolah nonaktif",
            "count": inactive_accounts.count(),
            "description": "Cek apakah akun memang harus dinonaktifkan atau perlu diaktifkan kembali.",
            "url": "/accounts/",
            "action_label": "Tinjau akun",
        },
    ]

    social_cards = [
        {
            "title": "Siswa yatim",
            "count": StudentProfile.objects.filter(is_active=True, family_status=StudentProfile.FamilyStatus.ORPHAN_FATHER).count(),
            "hint": "Perlu perhatian pada data wali dan bantuan yang relevan.",
        },
        {
            "title": "Siswa piatu",
            "count": StudentProfile.objects.filter(is_active=True, family_status=StudentProfile.FamilyStatus.ORPHAN_MOTHER).count(),
            "hint": "Pastikan nama wali dan dokumen pendukung terisi.",
        },
        {
            "title": "Yatim piatu",
            "count": StudentProfile.objects.filter(is_active=True, family_status=StudentProfile.FamilyStatus.ORPHAN_BOTH).count(),
            "hint": "Kelompok yang paling perlu monitoring berkelanjutan.",
        },
        {
            "title": "Punya KIP/PIP",
            "count": kip_number_students.count(),
            "hint": "Gunakan nomor KIP/PIP dari data siswa.",
        },
        {
            "title": "Upload kartu KIP/PIP",
            "count": kip_pip_documents.count(),
            "hint": "Dokumen tersimpan di tab upload berkas siswa.",
        },
        {
            "title": "Kebutuhan khusus",
            "count": special_needs_students.count(),
            "hint": "Bantu operator memantau layanan pendukung.",
        },
    ]

    compliance_cards = [
        {
            "title": "Data orang tua belum lengkap",
            "count": parents_missing.count(),
            "description": "Cek ayah atau ibu yang belum terisi agar arsip keluarga lebih rapi.",
        },
        {
            "title": "Siswa belum punya NIS",
            "count": StudentProfile.objects.filter(is_active=True).filter(Q(nis__isnull=True) | Q(nis="")).count(),
            "description": "Nomor induk penting untuk identifikasi cepat dan pelaporan.",
        },
        {
            "title": "Siswa belum punya NISN",
            "count": StudentProfile.objects.filter(is_active=True).filter(Q(nisn__isnull=True) | Q(nisn="")).count(),
            "description": "Lengkapi NISN agar data sinkron dengan referensi nasional.",
        },
        {
            "title": "Berkas siswa tersimpan",
            "count": StudentDocument.objects.count(),
            "description": "Semua dokumen siswa yang diunggah dari menu edit.",
        },
    ]

    priority_actions = []
    if not active_year:
        priority_actions.append(
            {
                "title": "Tetapkan tahun ajaran aktif",
                "description": "Dashboard akan lebih akurat setelah satu tahun ajaran aktif dipilih.",
                "url": "/academics/years/add/",
                "action_label": "Tambah tahun ajaran",
            }
        )
    priority_actions.append(
        {
            "title": "Buka kurikulum",
            "description": "Kelola struktur kurikulum, jadwal PBM, dan generator otomatis dari satu tempat.",
            "url": "/academics/curriculum/",
            "action_label": "Buka kurikulum",
        }
    )
    if groups_without_homeroom.exists():
        priority_actions.append(
            {
                "title": "Lengkapi wali kelas",
                "description": f"Ada {groups_without_homeroom.count()} rombel yang belum memiliki wali kelas.",
                "url": "/academics/",
                "action_label": "Atur wali kelas",
            }
        )
    if students_without_group.exists():
        priority_actions.append(
            {
                "title": "Masukkan siswa ke rombel",
                "description": f"Ada {students_without_group.count()} siswa aktif yang belum terhubung ke rombel.",
                "url": "/students/",
                "action_label": "Edit data siswa",
            }
        )
    if teachers_without_subject.exists():
        priority_actions.append(
            {
                "title": "Lengkapi mapel guru",
                "description": f"Ada {teachers_without_subject.count()} guru aktif yang mapelnya belum diisi.",
                "url": "/teachers/",
                "action_label": "Lengkapi guru",
            }
        )

    context = {
        "dashboard_mode": "admin",
        "student_count": StudentProfile.objects.count(),
        "teacher_count": TeacherProfile.objects.count(),
        "account_count": CustomUser.objects.count(),
        "study_group_count": StudyGroup.objects.count(),
        "homeroom_count": StudyGroup.objects.filter(homeroom_teacher__isnull=False).count(),
        "students_without_group_count": students_without_group.count(),
        "students_without_guardian_count": students_without_guardian.count(),
        "teachers_without_subject_count": teachers_without_subject.count(),
        "inactive_account_count": inactive_accounts.count(),
        "student_accounts": CustomUser.objects.filter(role=CustomUser.Role.STUDENT).count(),
        "teacher_accounts": CustomUser.objects.filter(role=CustomUser.Role.TEACHER).count(),
        "latest_students": StudentProfile.objects.select_related("user", "study_group").order_by("-created_at")[:5],
        "latest_teachers": TeacherProfile.objects.select_related("user").order_by("-created_at")[:5],
        "latest_groups": StudyGroup.objects.select_related(
            "school_class",
            "academic_year",
            "homeroom_teacher__user",
        ).order_by("-created_at")[:5],
        "active_year": active_year,
        "active_year_groups": active_year_groups[:6],
        "completion_cards": completion_cards,
        "social_cards": social_cards,
        "compliance_cards": compliance_cards,
        "health_cards": health_cards,
        "alert_cards": alert_cards,
        "priority_actions": priority_actions,
        "show_login_briefing": show_login_briefing,
        "login_briefing_actions": priority_actions[:4],
        "students_without_group": students_without_group.select_related("user")[:5],
        "teachers_without_subject": teachers_without_subject.select_related("user")[:5],
        "recent_activities": ActivityLog.objects.select_related("actor").order_by("-created_at")[:6],
    }
    return render(request, "dashboard/home.html", context)


@login_required
def workflow(request):
    active_year = AcademicYear.objects.filter(is_active=True).first()
    groups_without_homeroom = StudyGroup.objects.filter(is_active=True, homeroom_teacher__isnull=True)
    students_without_group = StudentProfile.objects.filter(is_active=True, study_group__isnull=True)
    teachers_without_subject = TeacherProfile.objects.filter(is_active=True).filter(
        Q(subject="") | Q(subject__isnull=True)
    )
    inactive_accounts = CustomUser.objects.filter(is_school_active=False)

    steps = _build_workflow_steps(
        active_year,
        groups_without_homeroom,
        students_without_group,
        teachers_without_subject,
        inactive_accounts,
    )

    context = {
        "active_year": active_year,
        "workflow_steps": steps,
        "workflow_complete_count": sum(1 for step in steps if step["count"] == 0),
        "workflow_total_count": len(steps),
    }
    return render(request, "dashboard/workflow.html", context)


@login_required
def health(request):
    return JsonResponse(
        {
            "ok": True,
            "checked_at": timezone.now().isoformat(),
            "user": request.user.username,
        }
    )


@login_required
def search(request):
    query = request.GET.get("q", "")
    results = _global_search(query)
    return render(
        request,
        "dashboard/search.html",
        {
            **results,
            "page_kicker": "Pencarian PDM",
            "page_title": "Cari data lintas modul",
            "page_description": "Temukan siswa, guru, rombel, dan tahun ajaran dari satu kotak pencarian.",
        },
    )
