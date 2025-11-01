from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0012_role_model_and_seed'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResearchArea',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, unique=True)),
                ('name', models.CharField(max_length=128)),
                ('summary', models.TextField(blank=True)),
                ('details', models.TextField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='research_areas/')),
                ('display_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'ordering': ['display_order', 'id'],
            },
        ),
    ]