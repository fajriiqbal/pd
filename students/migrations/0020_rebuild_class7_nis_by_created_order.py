from django.db import migrations, transaction


def rebuild_class7_nis_by_created_order(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    StudentProfile = apps.get_model("students", "StudentProfile")
    SchoolIdentity = apps.get_model("institution", "SchoolIdentity")

    identity = SchoolIdentity.objects.using(db_alias).first()
    prefix_root = (identity.nsm if identity and identity.nsm else "").strip()
    if not prefix_root:
        return

    class7_students = list(
        StudentProfile.objects.using(db_alias)
        .select_related("study_group__school_class", "user")
        .filter(entry_year=2025)
        .order_by("created_at", "pk")
    )

    if not class7_students:
        return

    with transaction.atomic(using=db_alias):
        StudentProfile.objects.using(db_alias).filter(pk__in=[student.pk for student in class7_students]).update(nis=None)

        sequence = 1
        for student in class7_students:
            student.nis = f"{prefix_root}25{sequence:04d}"
            sequence += 1
            student.save(update_fields=["nis"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0019_rebuild_class7_nis_sequence"),
    ]

    operations = [
        migrations.RunPython(rebuild_class7_nis_by_created_order, migrations.RunPython.noop),
    ]
