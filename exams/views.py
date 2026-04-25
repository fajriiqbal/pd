from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from academics.models import StudyGroup
from accounts.models import CustomUser
from institution.models import SchoolIdentity
from students.models import StudentProfile

from .forms import ExamPrintForm, ExamSessionForm
from .models import ExamSession


def _is_exam_admin(user):
    return bool(user.is_superuser or user.role in {CustomUser.Role.ADMIN, CustomUser.Role.TEACHER})


def _require_exam_admin(request):
    if not _is_exam_admin(request.user):
        raise PermissionDenied


def _active_session():
    return ExamSession.objects.select_related("academic_year").filter(is_active=True).first()


def _print_form(request):
    form = ExamPrintForm(request.GET or None)
    selected_session = None
    selected_group = None
    exam_date = request.GET.get("exam_date") or timezone.localdate().isoformat()
    room_name = request.GET.get("room_name", "")
    supervisor_name = request.GET.get("supervisor_name", "")

    if form.is_valid():
        selected_session = form.cleaned_data.get("session") or _active_session()
        selected_group = form.cleaned_data.get("study_group")
        exam_date = form.cleaned_data.get("exam_date") or timezone.localdate()
        room_name = form.cleaned_data.get("room_name", "")
        supervisor_name = form.cleaned_data.get("supervisor_name", "")
    else:
        if request.GET:
            selected_session = _active_session()
            selected_group = None

    return form, selected_session, selected_group, exam_date, room_name, supervisor_name


def _print_context(request, title, subtitle, extra=None):
    school_identity = SchoolIdentity.objects.first()
    active_session = _active_session()
    sessions = ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name")
    groups = StudyGroup.objects.select_related("academic_year", "school_class").filter(is_active=True).order_by(
        "school_class__level_order",
        "name",
    )
    context = {
        "page_kicker": "Menu Ujian",
        "page_title": title,
        "page_description": subtitle,
        "school_identity": school_identity,
        "active_exam_session": active_session,
        "exam_sessions": sessions,
        "exam_groups": groups,
    }
    if extra:
        context.update(extra)
    return context


@login_required
def overview(request):
    _require_exam_admin(request)
    active_session = _active_session()
    session_count = ExamSession.objects.count()
    group_count = StudyGroup.objects.filter(is_active=True).count()
    student_count = StudentProfile.objects.filter(is_active=True).count()

    context = _print_context(
        request,
        "Menu Ujian",
        "Satu tempat untuk menyiapkan sesi ujian dan mencetak kartu, absensi, BAP, serta label ruang.",
        {
            "active_exam_session": active_session,
            "session_count": session_count,
            "group_count": group_count,
            "student_count": student_count,
            "quick_actions": [
                {"title": "Cetak kartu ujian", "url": "exams:cards", "description": "Kartu per rombel untuk peserta ujian."},
                {"title": "Cetak daftar hadir", "url": "exams:attendance", "description": "Daftar hadir siap tanda tangan."},
                {"title": "Cetak BAP", "url": "exams:bap", "description": "Berita acara pelaksanaan ujian."},
                {"title": "Cetak label ruang", "url": "exams:room_label", "description": "Label besar untuk pintu atau meja ruang."},
            ],
        },
    )
    return render(request, "exams/overview.html", context)


@login_required
def session_list(request):
    _require_exam_admin(request)
    sessions = ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name")
    return render(
        request,
        "exams/session_list.html",
        _print_context(
            request,
            "Sesi Ujian",
            "Kelola nama sesi, tahun ajaran, dan status aktif yang dipakai semua dokumen ujian.",
            {"sessions": sessions},
        ),
    )


@login_required
def session_create(request):
    _require_exam_admin(request)
    form = ExamSessionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sesi ujian berhasil ditambahkan.")
        return redirect("exams:session_list")

    return render(
        request,
        "shared/form_page.html",
        {
            **_print_context(
                request,
                "Tambah sesi ujian",
                "Buat sesi ujian baru sebelum mencetak dokumen.",
            ),
            "form": form,
            "submit_label": "Simpan sesi",
            "cancel_url": "exams:session_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def session_update(request, pk):
    _require_exam_admin(request)
    session = get_object_or_404(ExamSession, pk=pk)
    form = ExamSessionForm(request.POST or None, instance=session)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sesi ujian berhasil diperbarui.")
        return redirect("exams:session_list")

    return render(
        request,
        "shared/form_page.html",
        {
            **_print_context(
                request,
                f"Edit sesi {session.name}",
                "Perbarui detail sesi ujian yang dipakai saat mencetak dokumen.",
            ),
            "form": form,
            "submit_label": "Simpan perubahan",
            "cancel_url": "exams:session_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def session_delete(request, pk):
    _require_exam_admin(request)
    session = get_object_or_404(ExamSession, pk=pk)
    if request.method == "POST":
        session.delete()
        messages.success(request, "Sesi ujian berhasil dihapus.")
        return redirect("exams:session_list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": session.name,
            "item_type": "sesi ujian",
            "cancel_url": "exams:session_list",
        },
    )


def _selected_exam_data(request):
    form, session, group, exam_date, room_name, supervisor_name = _print_form(request)
    if not session:
        session = _active_session()
    students = StudentProfile.objects.none()
    if session and group:
        students = (
            StudentProfile.objects.select_related("user", "study_group", "study_group__school_class")
            .filter(is_active=True, study_group=group)
            .order_by("user__full_name")
        )
    return form, session, group, exam_date, room_name, supervisor_name, students


@login_required
def print_cards(request):
    _require_exam_admin(request)
    form, session, group, exam_date, room_name, supervisor_name, students = _selected_exam_data(request)
    cards = [
        {
            "index": index + 1,
            "student": student,
            "participant_number": f"{session.id:02d}{group.id:02d}{index + 1:03d}" if session and group else "",
        }
        for index, student in enumerate(students)
    ]
    return render(
        request,
        "exams/print_cards.html",
        _print_context(
            request,
            "Cetak Kartu Ujian",
            "Pilih sesi dan rombel, lalu cetak kartu peserta ujian.",
            {
                "form": form,
                "selected_session": session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "cards": cards,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )


@login_required
def print_attendance(request):
    _require_exam_admin(request)
    form, session, group, exam_date, room_name, supervisor_name, students = _selected_exam_data(request)
    return render(
        request,
        "exams/print_attendance.html",
        _print_context(
            request,
            "Cetak Daftar Hadir",
            "Daftar hadir ujian untuk satu rombel, siap dicetak dan ditandatangani.",
            {
                "form": form,
                "selected_session": session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "students": students,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )


@login_required
def print_bap(request):
    _require_exam_admin(request)
    form, session, group, exam_date, room_name, supervisor_name, students = _selected_exam_data(request)
    school_identity = SchoolIdentity.objects.first()
    return render(
        request,
        "exams/print_bap.html",
        _print_context(
            request,
            "Cetak BAP",
            "Berita acara pelaksanaan ujian yang fokus pada catatan pelaksanaan, bukan penilaian.",
            {
                "form": form,
                "selected_session": session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "students": students,
                "school_identity": school_identity,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )


@login_required
def print_room_label(request):
    _require_exam_admin(request)
    form, session, group, exam_date, room_name, supervisor_name, _students = _selected_exam_data(request)
    room_name = room_name or (group.room_name if group else "")
    return render(
        request,
        "exams/print_room_label.html",
        _print_context(
            request,
            "Cetak Label Ruang",
            "Label besar untuk pintu atau meja ruang ujian.",
            {
                "form": form,
                "selected_session": session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )
