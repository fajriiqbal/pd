import re

from .models import TeacherAdditionalTask, TeacherProfile


def _task_text(task):
    parts = [task.name or "", task.description or ""]
    return " ".join(part for part in parts if part).casefold()


def get_headmaster_teacher():
    leadership_tasks = list(
        TeacherAdditionalTask.objects.select_related("teacher__user")
        .filter(task_type=TeacherAdditionalTask.TaskType.LEADERSHIP, is_active=True)
        .order_by("-start_date", "-created_at")
    )
    if not leadership_tasks:
        return None

    keywords = re.compile(r"(kepala\s*madrasah|kamad|kepala\s*sekolah)", re.IGNORECASE)
    matched_tasks = [task for task in leadership_tasks if keywords.search(_task_text(task))]
    if len(matched_tasks) == 1:
        return matched_tasks[0].teacher
    if len(matched_tasks) > 1:
        return matched_tasks[0].teacher

    if len(leadership_tasks) == 1:
        return leadership_tasks[0].teacher

    # Ambigu kalau ada lebih dari satu tugas pimpinan aktif tanpa penanda "kepala madrasah".
    return leadership_tasks[0].teacher


def get_headmaster_display_name():
    teacher = get_headmaster_teacher()
    if not teacher:
        return ""
    return teacher.user.full_name

