from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0017_news_awards'),
    ]

    operations = [
        migrations.AddField(
            model_name='labaward',
            name='image',
            field=models.ImageField(upload_to='awards/', null=True, blank=True),
        ),
    ]