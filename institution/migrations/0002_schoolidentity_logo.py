from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("institution", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolidentity",
            name="logo",
            field=models.ImageField(blank=True, upload_to="institution/", verbose_name="Logo madrasah"),
        ),
    ]
