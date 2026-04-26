from django.db import migrations
from django.db.models import Q


def fill_student_nis_from_nsm(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    StudentProfile = apps.get_model("students", "StudentProfile")
    SchoolIdentity = apps.get_model("institution", "SchoolIdentity")

    identity = SchoolIdentity.objects.using(db_alias).order_by("pk").first()
    prefix = (identity.nsm if identity and identity.nsm else "").strip()
    if not prefix:
        return

    existing_numbers = []
    for existing_nis in StudentProfile.objects.using(db_alias).exclude(nis__isnull=True).exclude(nis="").values_list("nis", flat=True):
        existing_nis = str(existing_nis)
        if existing_nis.startswith(prefix):
            suffix = existing_nis[len(prefix):]
            if suffix.isdigit():
                existing_numbers.append(int(suffix))

    next_number = (max(existing_numbers) if existing_numbers else 0) + 1
    blank_students = list(
        StudentProfile.objects.using(db_alias)
        .filter(Q(nis__isnull=True) | Q(nis=""))
        .select_related("study_group__school_class", "user")
    )
    blank_students.sort(
        key=lambda student: (
            student.study_group.school_class.level_order if student.study_group and student.study_group.school_class else 9999,
            student.study_group.name if student.study_group else "",
            student.user.full_name if student.user_id else "",
            student.pk,
        )
    )

    for student in blank_students:
        student.nis = f"{prefix}{next_number:04d}"
        next_number += 1
        student.save(update_fields=["nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0012_studentalumnivalidation_system_fields"),
        ("institution", "0002_schoolidentity_logo"),
    ]

    operations = [
        migrations.RunPython(fill_student_nis_from_nsm, migrations.RunPython.noop),
    ]
