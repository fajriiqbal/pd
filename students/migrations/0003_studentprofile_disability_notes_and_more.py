from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0002_studentprofile_study_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="disability_notes",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="father_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="kip_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="mother_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="special_needs",
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
