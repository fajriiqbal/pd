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

from .forms import ExamPrintForm, ExamScheduleItemForm, ExamSessionForm
from .models import ExamScheduleItem, ExamSession


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
    selected_schedule_session = None
    selected_group = None
    exam_date = request.GET.get("exam_date") or timezone.localdate().isoformat()
    room_name = request.GET.get("room_name", "")
    supervisor_name = request.GET.get("supervisor_name", "")

    if form.is_valid():
        selected_session = form.cleaned_data.get("session") or _active_session()
        selected_schedule_session = form.cleaned_data.get("schedule_session") or selected_session
        selected_group = form.cleaned_data.get("study_group")
        exam_date = form.cleaned_data.get("exam_date") or timezone.localdate()
        room_name = form.cleaned_data.get("room_name", "")
        supervisor_name = form.cleaned_data.get("supervisor_name", "")
    else:
        if request.GET:
            selected_session = _active_session()
            selected_schedule_session = selected_session
            selected_group = None

    if not selected_schedule_session:
        selected_schedule_session = selected_session

    return form, selected_session, selected_schedule_session, selected_group, exam_date, room_name, supervisor_name


def _session_schedule(session):
    if not session:
        return ExamScheduleItem.objects.none()
    return (
        ExamScheduleItem.objects.select_related("session", "session__academic_year")
        .filter(session=session, is_active=True)
        .order_by("exam_date", "start_time", "sort_order", "title")
    )


def _chunk_cards(cards, size=4):
    return [cards[index : index + size] for index in range(0, len(cards), size)]


def _print_context(request, title, subtitle, extra=None):
    school_identity = SchoolIdentity.objects.first()
    active_session = _active_session()
    sessions = ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name")
    schedule_session = extra.get("selected_schedule_session") if extra else None
    schedule_items = _session_schedule(schedule_session or active_session)
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
        "selected_schedule_session": schedule_session or active_session,
        "schedule_items": schedule_items,
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
                {"title": "Jadwal ujian", "url": "exams:schedule_list", "description": "Atur mapel, jam ujian, dan istirahat."},
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
def schedule_list(request):
    _require_exam_admin(request)
    session_id = request.GET.get("session")
    selected_session = (
        get_object_or_404(ExamSession, pk=session_id)
        if session_id
        else _active_session()
    )
    items = ExamScheduleItem.objects.select_related("session", "session__academic_year").order_by(
        "exam_date",
        "start_time",
        "sort_order",
        "title",
    )
    if selected_session:
        items = items.filter(session=selected_session)
    else:
        items = items.none()
    return render(
        request,
        "exams/schedule_list.html",
        _print_context(
            request,
            "Jadwal Ujian",
            "Susun urutan mapel, jam ujian, dan waktu istirahat untuk kartu peserta dan dokumen cetak.",
            {
                "sessions": ExamSession.objects.select_related("academic_year").order_by("-is_active", "-start_date", "name"),
                "selected_session": selected_session,
                "schedule_items": items,
            },
        ),
    )


@login_required
def schedule_create(request):
    _require_exam_admin(request)
    form = ExamScheduleItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Jadwal ujian berhasil ditambahkan.")
        return redirect("exams:schedule_list")

    return render(
        request,
        "shared/form_page.html",
        {
            **_print_context(
                request,
                "Tambah jadwal ujian",
                "Tambahkan mapel, jam ujian, atau jeda istirahat untuk sesi yang dipilih.",
            ),
            "form": form,
            "submit_label": "Simpan jadwal",
            "cancel_url": "exams:schedule_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def schedule_update(request, pk):
    _require_exam_admin(request)
    schedule_item = get_object_or_404(ExamScheduleItem, pk=pk)
    form = ExamScheduleItemForm(request.POST or None, instance=schedule_item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Jadwal ujian berhasil diperbarui.")
        return redirect("exams:schedule_list")

    return render(
        request,
        "shared/form_page.html",
        {
            **_print_context(
                request,
                f"Edit jadwal {schedule_item.title}",
                "Perbarui jam, judul mapel, atau tanda istirahat.",
            ),
            "form": form,
            "submit_label": "Simpan perubahan",
            "cancel_url": "exams:schedule_list",
            "checkbox_fields": ["is_active"],
        },
    )


@login_required
def schedule_delete(request, pk):
    _require_exam_admin(request)
    schedule_item = get_object_or_404(ExamScheduleItem, pk=pk)
    if request.method == "POST":
        schedule_item.delete()
        messages.success(request, "Jadwal ujian berhasil dihapus.")
        return redirect("exams:schedule_list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": schedule_item.title,
            "item_type": "jadwal ujian",
            "cancel_url": "exams:schedule_list",
        },
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
    form, session, schedule_session, group, exam_date, room_name, supervisor_name = _print_form(request)
    if not session:
        session = _active_session()
    students = StudentProfile.objects.none()
    if session and group:
        students = (
            StudentProfile.objects.select_related("user", "study_group", "study_group__school_class")
            .filter(is_active=True, study_group=group)
            .order_by("user__full_name")
        )
    schedule_items = _session_schedule(schedule_session or session)
    return form, session, schedule_session or session, group, exam_date, room_name, supervisor_name, students, schedule_items


@login_required
def print_cards(request):
    _require_exam_admin(request)
    form, session, schedule_session, group, exam_date, room_name, supervisor_name, students, schedule_items = _selected_exam_data(request)
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
                "selected_schedule_session": schedule_session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "cards": cards,
                "card_pages": _chunk_cards(cards, 4),
                "schedule_items": schedule_items,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )


@login_required
def print_attendance(request):
    _require_exam_admin(request)
    form, session, schedule_session, group, exam_date, room_name, supervisor_name, students, schedule_items = _selected_exam_data(request)
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
                "selected_schedule_session": schedule_session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "students": students,
                "schedule_items": schedule_items,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )


@login_required
def print_bap(request):
    _require_exam_admin(request)
    form, session, schedule_session, group, exam_date, room_name, supervisor_name, students, schedule_items = _selected_exam_data(request)
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
                "selected_schedule_session": schedule_session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "students": students,
                "schedule_items": schedule_items,
                "school_identity": school_identity,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )


@login_required
def print_room_label(request):
    _require_exam_admin(request)
    form, session, schedule_session, group, exam_date, room_name, supervisor_name, _students, schedule_items = _selected_exam_data(request)
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
                "selected_schedule_session": schedule_session,
                "selected_group": group,
                "exam_date": exam_date,
                "room_name": room_name,
                "supervisor_name": supervisor_name,
                "schedule_items": schedule_items,
                "print_requested": request.GET.get("print") == "1",
            },
        ),
    )
