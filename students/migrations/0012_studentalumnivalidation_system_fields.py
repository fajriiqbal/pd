from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0011_alter_studentdocument_document_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentalumnivalidation",
            name="government_birth_date",
            field=models.DateField(blank=True, help_text="Tanggal lahir sesuai data sistem yang dijadikan pembanding.", null=True),
        ),
        migrations.AddField(
            model_name="studentalumnivalidation",
            name="government_father_name",
            field=models.CharField(blank=True, help_text="Nama ayah sesuai data sistem yang dijadikan pembanding.", max_length=150),
        ),
        migrations.AddField(
            model_name="studentalumnivalidation",
            name="government_nisn",
            field=models.CharField(blank=True, help_text="NISN sesuai data sistem yang dijadikan pembanding.", max_length=30),
        ),
    ]
