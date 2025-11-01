from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0019_userprofile_selected_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='professional_summary',
            field=models.TextField(blank=True),
        ),
    ]