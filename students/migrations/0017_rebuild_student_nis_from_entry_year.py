from django.db import migrations, transaction


def rebuild_student_nis_from_entry_year(apps, schema_editor):
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
            "entry_year",
            "study_group__school_class__level_order",
            "study_group__name",
            "user__full_name",
            "pk",
        )
    )

    StudentProfile.objects.using(db_alias).update(nis=None)

    counters_by_prefix: dict[str, int] = {}
    with transaction.atomic(using=db_alias):
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
        ("students", "0016_fix_student_entry_year_by_current_class"),
    ]

    operations = [
        migrations.RunPython(rebuild_student_nis_from_entry_year, migrations.RunPython.noop),
    ]
