from django.db import migrations


def seed_research_areas(apps, schema_editor):
    import os
    from django.conf import settings
    from django.core.files import File

    ResearchArea = apps.get_model('lab', 'ResearchArea')

    # key, name, filename, order, summary, details
    areas = [
        (
            'computer_vision',
            'Computer Vision',
            'Computer Vision.jpg',
            0,
            'Algorithms and systems for visual understanding and perception.',
            ''
        ),
        (
            'medical_image_analysis',
            'Medical Image Analysis',
            'Medical Image Analysis.png',
            1,
            'Imaging, segmentation, and diagnostics for medical data.',
            ''
        ),
        (
            'remote_sensing',
            'Remote Sensing',
            'Remote Sensing.webp',
            2,
            'Earth observation and geospatial analysis from aerial and satellite imagery.',
            ''
        ),
        (
            'computational_biology_bioinformatics',
            'Computational Biology and Bioinformatics',
            'Computational Biology and Bioinformatics.jpg',
            3,
            'Data-driven modeling and analysis of biological systems.',
            ''
        ),
        (
            'image_processing',
            'Image Processing',
            'Image Processing.jpg',
            4,
            'Signal and image enhancement, restoration, and transformation techniques.',
            ''
        ),
    ]

    static_image_dir = os.path.join(settings.BASE_DIR, 'static', 'image')

    for key, name, filename, order, summary, details in areas:
        ra, created = ResearchArea.objects.get_or_create(
            key=key,
            defaults={
                'name': name,
                'summary': summary,
                'details': details,
                'display_order': order,
            }
        )
        # If it already existed, keep existing name/order but fill summary/details if empty
        if not created:
            changed = False
            if not ra.summary and summary:
                ra.summary = summary
                changed = True
            if not ra.details and details:
                ra.details = details
                changed = True
            if changed:
                ra.save()

        # Attach image from static/image if present and no image set yet
        if not ra.image and filename:
            image_path = os.path.join(static_image_dir, filename)
            if os.path.exists(image_path):
                with open(image_path, 'rb') as f:
                    ra.image.save(filename, File(f), save=True)


class Migration(migrations.Migration):
    dependencies = [
        ('lab', '0013_research_area_model'),
    ]

    operations = [
        migrations.RunPython(seed_research_areas, migrations.RunPython.noop),
    ]