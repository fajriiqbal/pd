import json
import random
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from academics.models import StudyGroup
from accounts.models import CustomUser
from institution.models import SchoolIdentity
from students.models import StudentProfile

from .forms import ExamPrintForm, ExamScheduleGenerateForm, ExamScheduleItemForm, ExamSessionForm
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


def _parse_subject_lines(raw_text):
    return [line.strip(" -•\t") for line in (raw_text or "").splitlines() if line.strip()]


def _parse_subject_lines(raw_text):
    subjects = []
    for line in (raw_text or "").splitlines():
        cleaned = line.strip().lstrip("-•*").strip()
        if cleaned:
            subjects.append(cleaned)
    return subjects


def _max_sessions_for_window(exam_start_time, exam_end_time, exam_duration_minutes, break_minutes):
    start_dt = datetime.combine(datetime.today(), exam_start_time)
    end_dt = datetime.combine(datetime.today(), exam_end_time)
    if end_dt <= start_dt:
        return 0

    slots = 0
    cursor = start_dt
    while True:
        exam_end_dt = cursor + timedelta(minutes=exam_duration_minutes)
        if exam_end_dt > end_dt:
            break
        slots += 1
        cursor = exam_end_dt + timedelta(minutes=break_minutes)
    return slots


def _build_schedule_preview(session, start_date, subjects, day_count, sessions_per_day, exam_start_time, exam_end_time, exam_duration_minutes, break_minutes):
    rng = random.Random()
    pool = subjects[:]
    rng.shuffle(pool)

    window_slots = _max_sessions_for_window(exam_start_time, exam_end_time, exam_duration_minutes, break_minutes)
    effective_sessions_per_day = min(sessions_per_day, window_slots) if window_slots else 0
    required_exam_slots = day_count * effective_sessions_per_day
    if required_exam_slots <= 0:
        return []

    generated_subjects = []
    while len(generated_subjects) < required_exam_slots:
        batch = subjects[:]
        rng.shuffle(batch)
        generated_subjects.extend(batch)
    generated_subjects = generated_subjects[:required_exam_slots]

    rows = []
    subject_index = 0
    current_date = start_date
    for _day in range(day_count):
        current_dt = datetime.combine(current_date, exam_start_time)
        for slot_index in range(effective_sessions_per_day):
            subject_name = generated_subjects[subject_index]
            subject_index += 1
            end_dt = current_dt + timedelta(minutes=exam_duration_minutes)
            rows.append(
                {
                    "session_id": session.pk,
                    "exam_date": current_date.isoformat(),
                    "start_time": current_dt.time().isoformat(timespec="minutes"),
                    "end_time": end_dt.time().isoformat(timespec="minutes"),
                    "title": subject_name,
                    "item_type": ExamScheduleItem.ItemType.EXAM,
                    "description": "",
                    "sort_order": len(rows) + 1,
                }
            )
            current_dt = end_dt
            if slot_index < effective_sessions_per_day - 1:
                break_end_dt = current_dt + timedelta(minutes=break_minutes)
                rows.append(
                    {
                        "session_id": session.pk,
                        "exam_date": current_date.isoformat(),
                        "start_time": current_dt.time().isoformat(timespec="minutes"),
                        "end_time": break_end_dt.time().isoformat(timespec="minutes"),
                        "title": "Istirahat",
                        "item_type": ExamScheduleItem.ItemType.BREAK,
                        "description": f"Istirahat {break_minutes} menit",
                        "sort_order": len(rows) + 1,
                    }
                )
                current_dt = break_end_dt
        current_date = current_date + timedelta(days=1)

    return rows


def _save_generated_schedule(session, preview_rows):
    with transaction.atomic():
        ExamScheduleItem.objects.filter(session=session).delete()
        created = []
        for row in preview_rows:
            created.append(
                ExamScheduleItem.objects.create(
                    session=session,
                    exam_date=row["exam_date"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    title=row["title"],
                    item_type=row["item_type"],
                    description=row.get("description", ""),
                    sort_order=row.get("sort_order", 1),
                    is_active=True,
                )
                )
    return created


def _load_preview_rows(raw_payload):
    if not raw_payload:
        return []

    try:
        preview_rows = json.loads(raw_payload)
    except json.JSONDecodeError:
        return []

    if not isinstance(preview_rows, list):
        return []

    normalized_rows = []
    for row in preview_rows:
        if not isinstance(row, dict):
            continue
        normalized_rows.append(
            {
                "session_id": row.get("session_id"),
                "exam_date": row.get("exam_date"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "title": row.get("title", ""),
                "item_type": row.get("item_type", ExamScheduleItem.ItemType.EXAM),
                "description": row.get("description", ""),
                "sort_order": row.get("sort_order", 1),
            }
        )
    return normalized_rows


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
def schedule_generate(request):
    _require_exam_admin(request)
    form = ExamScheduleGenerateForm(request.POST or None)
    preview_rows = []
    selected_session = None
    generated_subjects = []

    if request.method == "POST" and form.is_valid():
        selected_session = form.cleaned_data["session"]
        start_date = form.cleaned_data["start_date"]
        day_count = form.cleaned_data["day_count"]
        sessions_per_day = form.cleaned_data["sessions_per_day"]
        exam_start_time = form.cleaned_data["exam_start_time"]
        exam_end_time = form.cleaned_data["exam_end_time"]
        exam_duration_minutes = form.cleaned_data["exam_duration_minutes"]
        break_minutes = form.cleaned_data["break_minutes"]
        subjects = _parse_subject_lines(form.cleaned_data["subjects_text"])
        if not subjects:
            form.add_error("subjects_text", "Minimal satu mata pelajaran harus diisi.")
        else:
            preview_rows = _build_schedule_preview(
                selected_session,
                start_date,
                subjects,
                day_count,
                sessions_per_day,
                exam_start_time,
                exam_end_time,
                exam_duration_minutes,
                break_minutes,
            )
            window_slots = _max_sessions_for_window(exam_start_time, exam_end_time, exam_duration_minutes, break_minutes)
            if not window_slots:
                form.add_error("exam_end_time", "Jam selesai harus lebih besar dari jam mulai dan cukup untuk menampung minimal satu mapel.")
            else:
                effective_sessions_per_day = min(sessions_per_day, window_slots)
                if effective_sessions_per_day < sessions_per_day:
                    messages.warning(
                        request,
                        f"Rentang jam hanya muat {effective_sessions_per_day} mapel per hari, jadi hasil generate disesuaikan otomatis.",
                    )
                generated_subjects = subjects

                if request.POST.get("action") == "save":
                    saved_preview_rows = _load_preview_rows(request.POST.get("preview_payload"))
                    if not saved_preview_rows:
                        form.add_error(None, "Preview jadwal tidak ditemukan. Silakan generate ulang dulu.")
                    else:
                        _save_generated_schedule(selected_session, saved_preview_rows)
                        messages.success(request, "Jadwal ujian otomatis berhasil disimpan.")
                        return redirect(f"{reverse('exams:schedule_list')}?session={selected_session.pk}")

    preview_json = json.dumps(preview_rows) if preview_rows else ""
    return render(
        request,
        "exams/schedule_generate.html",
        _print_context(
            request,
            "Generate Jadwal Ujian",
            "Buat jadwal 6 hari secara otomatis, lalu ulangi generate sampai susunannya sesuai.",
            {
                "form": form,
                "preview_rows": preview_rows,
                "preview_json": preview_json,
                "selected_session": selected_session,
                "generated_subjects": generated_subjects,
            },
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
