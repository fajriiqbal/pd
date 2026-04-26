from django.db import migrations, transaction


def rebuild_student_nis_by_nsm_entry_year(apps, schema_editor):
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
            effective_entry_year = student.entry_year
            if student.study_group_id and student.study_group.school_class_id:
                academic_year = getattr(student.study_group, "academic_year", None)
                base_year = int(str(academic_year.start_date)[:4]) if academic_year and academic_year.start_date else None
                level_order = student.study_group.school_class.level_order

                if base_year and 7 <= level_order <= 9:
                    effective_entry_year = base_year - max(level_order - 7, 0)

            if not effective_entry_year:
                continue

            prefix = f"{prefix_root}{int(effective_entry_year) % 100:02d}"
            next_number = counters_by_prefix.get(prefix, 0) + 1
            student.nis = f"{prefix}{next_number:04d}"
            counters_by_prefix[prefix] = next_number
            student.save(update_fields=["nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0014_rebuild_student_nis_by_nsm_and_entry_year"),
    ]

    operations = [
        migrations.RunPython(rebuild_student_nis_by_nsm_entry_year, migrations.RunPython.noop),
    ]
