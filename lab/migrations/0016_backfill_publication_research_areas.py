from django.db import migrations


def backfill_research_areas(apps, schema_editor):
    Publication = apps.get_model('lab', 'Publication')
    ResearchArea = apps.get_model('lab', 'ResearchArea')
    for pub in Publication.objects.all().iterator():
        key = (pub.research_area or '').strip()
        if not key:
            continue
        ra = ResearchArea.objects.filter(key=key).first()
        if ra:
            pub.research_areas.add(ra)


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0015_publication_m2m_objective_ongoing_and_contributions'),
    ]

    operations = [
        migrations.RunPython(backfill_research_areas, migrations.RunPython.noop),
    ]