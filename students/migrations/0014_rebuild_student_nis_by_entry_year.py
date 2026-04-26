from django.db import migrations


def rebuild_student_nis_by_entry_year(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    StudentProfile = apps.get_model("students", "StudentProfile")

    students = list(
        StudentProfile.objects.using(db_alias)
        .select_related("study_group__school_class", "user")
        .order_by(
            "entry_year",
            "study_group__school_class__level_order",
            "study_group__name",
            "user__full_name",
            "pk",
        )
    )

    # Clear first so unique NIS values can be reassigned safely.
    StudentProfile.objects.using(db_alias).update(nis=None)

    counters: dict[str, int] = {}
    for student in students:
        if not student.entry_year:
            continue

        prefix = f"{int(student.entry_year) % 100:02d}"
        next_number = counters.get(prefix, 0) + 1
        student.nis = f"{prefix}{next_number:04d}"
        counters[prefix] = next_number
        student.save(update_fields=["nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0013_fill_student_nis_from_entry_year"),
    ]

    operations = [
        migrations.RunPython(rebuild_student_nis_by_entry_year, migrations.RunPython.noop),
    ]
