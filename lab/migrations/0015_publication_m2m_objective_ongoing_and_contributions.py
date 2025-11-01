from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0014_seed_research_areas'),
    ]

    operations = [
        migrations.AddField(
            model_name='publication',
            name='research_areas',
            field=models.ManyToManyField(blank=True, related_name='publications', to='lab.researcharea'),
        ),
        migrations.AddField(
            model_name='publication',
            name='is_ongoing',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='publication',
            name='objective',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.CreateModel(
            name='PublicationContribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=300)),
                ('publication', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contributions', to='lab.publication')),
            ],
        ),
    ]