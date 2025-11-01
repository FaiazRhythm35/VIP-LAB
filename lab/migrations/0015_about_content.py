from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0014_seed_research_areas'),
    ]

    operations = [
        migrations.CreateModel(
            name='AboutContent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Visual Image Processing Lab (VIP Lab)', max_length=200)),
                ('summary', models.TextField(blank=True)),
                ('aim', models.TextField(blank=True)),
                ('mission', models.TextField(blank=True)),
                ('vision', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'About Content',
                'verbose_name_plural': 'About Content',
            },
        ),
    ]