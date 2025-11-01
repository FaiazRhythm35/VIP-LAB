from django.db import migrations, models


def seed_roles(apps, schema_editor):
    Role = apps.get_model('lab', 'Role')
    defaults = [
        ('principal_investigator', 'Principal Investigator', 0),
        ('assistant_pi', 'Assistant Principal Investigator', 1),
        ('research_assistant', 'Research Assistant', 2),
        ('graduate_student', 'Graduate Student', 3),
        ('alumni', 'Alumni', 4),
    ]
    for key, name, order in defaults:
        Role.objects.get_or_create(key=key, defaults={'name': name, 'display_order': order})


class Migration(migrations.Migration):
    dependencies = [
        ('lab', '0011_publication_show_on_public_pages'),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, unique=True)),
                ('name', models.CharField(max_length=128)),
                ('display_order', models.PositiveIntegerField(default=0)),
            ],
            options={'ordering': ['display_order', 'id']},
        ),
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]