from django.db import migrations
from django.db.models import Q


def fill_student_nis_from_entry_year(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    StudentProfile = apps.get_model("students", "StudentProfile")

    students = list(
        StudentProfile.objects.using(db_alias)
        .filter(Q(nis__isnull=True) | Q(nis=""))
        .select_related("study_group__school_class", "user")
    )
    students.sort(
        key=lambda student: (
            student.entry_year or 9999,
            student.study_group.school_class.level_order if student.study_group and student.study_group.school_class else 9999,
            student.study_group.name if student.study_group else "",
            student.user.full_name if student.user_id else "",
            student.pk,
        )
    )

    existing_numbers_by_prefix: dict[str, int] = {}
    for existing_nis, entry_year in StudentProfile.objects.using(db_alias).exclude(nis__isnull=True).exclude(nis="").values_list("nis", "entry_year"):
        prefix = f"{int(entry_year) % 100:02d}" if entry_year else str(existing_nis)[:2]
        suffix = str(existing_nis)[2:]
        if suffix.isdigit():
            current = int(suffix)
            existing_numbers_by_prefix[prefix] = max(existing_numbers_by_prefix.get(prefix, 0), current)

    for student in students:
        if not student.entry_year:
            continue

        prefix = f"{int(student.entry_year) % 100:02d}"
        next_number = existing_numbers_by_prefix.get(prefix, 0) + 1
        student.nis = f"{prefix}{next_number:04d}"
        existing_numbers_by_prefix[prefix] = next_number
        student.save(update_fields=["nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0013_fill_student_nis_from_entry_year"),
    ]

    operations = [
        migrations.RunPython(fill_student_nis_from_entry_year, migrations.RunPython.noop),
    ]
