import re

from django.db import migrations, transaction


def _infer_level_order(student):
    if student.study_group_id and student.study_group.school_class_id:
        return student.study_group.school_class.level_order

    class_label = (student.class_name or "").strip()
    match = re.search(r"(\d{1,2})", class_label)
    if match:
        return int(match.group(1))
    return None


def realign_entry_year_and_nis(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    StudentProfile = apps.get_model("students", "StudentProfile")
    SchoolIdentity = apps.get_model("institution", "SchoolIdentity")

    identity = SchoolIdentity.objects.using(db_alias).first()
    prefix_root = (identity.nsm if identity and identity.nsm else "").strip()
    if not prefix_root:
        return

    students = list(
        StudentProfile.objects.using(db_alias)
        .select_related("study_group__school_class", "user")
        .order_by(
            "study_group__school_class__level_order",
            "study_group__name",
            "class_name",
            "user__full_name",
            "pk",
        )
    )

    with transaction.atomic(using=db_alias):
        for student in students:
            level_order = _infer_level_order(student)
            if level_order in {7, 8, 9}:
                student.entry_year = 2025 - (level_order - 7)
                student.save(update_fields=["entry_year"])

        StudentProfile.objects.using(db_alias).update(nis=None)

        counters_by_prefix: dict[str, int] = {}
        for student in students:
            if not student.entry_year:
                continue

            prefix = f"{prefix_root}{int(student.entry_year) % 100:02d}"
            next_number = counters_by_prefix.get(prefix, 0) + 1
            student.nis = f"{prefix}{next_number:04d}"
            counters_by_prefix[prefix] = next_number
            student.save(update_fields=["nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0017_rebuild_student_nis_from_entry_year"),
    ]

    operations = [
        migrations.RunPython(realign_entry_year_and_nis, migrations.RunPython.noop),
    ]
