from django.db import migrations, transaction


def _infer_level_order(student):
    if student.study_group_id and student.study_group.school_class_id:
        return student.study_group.school_class.level_order

    class_label = (student.class_name or "").strip()
    for idx, char in enumerate(class_label):
        if char.isdigit():
            digits = []
            for follow in class_label[idx:]:
                if follow.isdigit() and len(digits) < 2:
                    digits.append(follow)
                else:
                    break
            if digits:
                return int("".join(digits))
    return None


def rebuild_class7_nis_sequence(apps, schema_editor):
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
        .order_by("study_group__name", "class_name", "user__full_name", "pk")
    )

    class7_students = [student for student in students if _infer_level_order(student) == 7]
    if not class7_students:
        return

    for student in class7_students:
        student.entry_year = 2025

    with transaction.atomic(using=db_alias):
        StudentProfile.objects.using(db_alias).filter(pk__in=[student.pk for student in class7_students]).update(nis=None)

        sequence = 1
        for student in class7_students:
            student.nis = f"{prefix_root}25{sequence:04d}"
            sequence += 1
            student.save(update_fields=["entry_year", "nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0018_realign_entry_year_and_nis_by_class_level"),
    ]

    operations = [
        migrations.RunPython(rebuild_class7_nis_sequence, migrations.RunPython.noop),
    ]
