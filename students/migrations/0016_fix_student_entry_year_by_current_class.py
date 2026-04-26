from django.db import migrations, transaction


def fix_student_entry_year_by_current_class(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    StudentProfile = apps.get_model("students", "StudentProfile")

    students = list(
        StudentProfile.objects.using(db_alias)
        .select_related("study_group__school_class", "study_group__academic_year", "user")
        .order_by(
            "study_group__school_class__level_order",
            "study_group__name",
            "user__full_name",
            "pk",
        )
    )

    updates = []
    for student in students:
        if not student.study_group_id or not student.study_group.school_class_id:
            continue

        level_order = student.study_group.school_class.level_order
        academic_year = getattr(student.study_group, "academic_year", None)
        start_year = int(str(academic_year.start_date)[:4]) if academic_year and academic_year.start_date else None
        if not start_year or not 7 <= level_order <= 9:
            continue

        expected_entry_year = start_year - max(level_order - 7, 0)
        if student.entry_year != expected_entry_year:
            student.entry_year = expected_entry_year
            updates.append(student)

    with transaction.atomic(using=db_alias):
        for student in updates:
            student.save(update_fields=["entry_year"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0015_rebuild_student_nis_by_nsm_entry_year"),
    ]

    operations = [
        migrations.RunPython(fix_student_entry_year_by_current_class, migrations.RunPython.noop),
    ]
