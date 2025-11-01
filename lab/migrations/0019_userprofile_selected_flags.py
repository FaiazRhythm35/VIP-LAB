from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0018_labaward_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='selected_alumni',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='selected_graduate_student',
            field=models.BooleanField(default=False),
        ),
    ]