from django.db import migrations


def seed_rombel_teaching_assignments(apps, schema_editor):
    StudyGroup = apps.get_model("academics", "StudyGroup")
    ClassSubject = apps.get_model("academics", "ClassSubject")
    RombelTeachingAssignment = apps.get_model("academics", "RombelTeachingAssignment")

    active_groups = (
        StudyGroup.objects.select_related("academic_year", "school_class")
        .filter(is_active=True, academic_year__is_active=True)
    )

    for study_group in active_groups:
        class_subjects = ClassSubject.objects.select_related("teacher").filter(
            school_class=study_group.school_class,
            is_active=True,
        )
        for class_subject in class_subjects:
            RombelTeachingAssignment.objects.get_or_create(
                study_group=study_group,
                subject_id=class_subject.subject_id,
                defaults={
                    "teacher_id": class_subject.teacher_id,
                    "minimum_score": class_subject.minimum_score,
                    "weekly_hours": class_subject.weekly_hours,
                    "notes": class_subject.notes,
                    "is_active": class_subject.is_active,
                },
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0005_rombelteachingassignment"),
        ("teachers", "0006_teacherarchive_teachermutationrecord"),
    ]

    operations = [
        migrations.RunPython(seed_rombel_teaching_assignments, noop_reverse),
    ]
