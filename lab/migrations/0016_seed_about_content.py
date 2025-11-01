from django.db import migrations


def seed_about(apps, schema_editor):
    AboutContent = apps.get_model('lab', 'AboutContent')

    summary = (
        "The Visual Image Processing Lab (VIP Lab) explores the fundamental mechanisms of how visual "
        "information is perceived, processed, analyzed, stored, and recalled, aiming to bridge human visual "
        "cognition with computational intelligence. Our research focuses on intelligent behavior understanding, "
        "vision-based decision support systems, and biomedical image computing for enhanced diagnostic insight. "
        "The lab also emphasizes developing advanced visual information protection methods, including data hiding "
        "and multimedia security, to ensure data integrity and confidentiality. Through interdisciplinary innovation, "
        "VIP Lab strives to become a leading research center in visual perception and computational imaging, driving "
        "the next generation of intelligent, secure, and interpretable vision-based systems for real-world and societal advancement."
    )

    title = "Visual Image Processing Lab (VIP Lab)"

    aim = (
        "The Visual Image Processing Lab aims to explore and model the fundamental mechanisms through which "
        "visual information is perceived, processed, analyzed, stored, and recalled. The goal is to bridge the gap "
        "between human visual cognition and computational intelligence to develop efficient and interpretable vision-based systems."
    )

    mission = (
        "Our mission is to advance research in the areas of:\n\n"
        "- Intelligent behavior understanding through vision-based analysis.\n"
        "- Vision-driven decision support systems for complex real-world scenarios.\n"
        "- Biomedical image computing and analysis, enhancing diagnostic accuracy and medical insight.\n\n"
        "We are also committed to developing robust visual information protection techniques, including data hiding "
        "and multimedia security solutions, that ensure both the reliability and confidentiality of visual data."
    )

    vision = (
        "The VIP Lab envisions becoming a leading research hub for visual perception and computational imaging, "
        "integrating principles of human cognition, artificial intelligence, and information security. Through "
        "interdisciplinary innovation, we aspire to contribute to the next generation of intelligent systems capable of "
        "understanding, protecting, and utilizing visual information effectively for societal and technological advancement."
    )

    obj = AboutContent.objects.first()
    if obj:
        changed = False
        if not obj.summary:
            obj.summary = summary
            changed = True
        if not obj.title:
            obj.title = title
            changed = True
        if not obj.aim:
            obj.aim = aim
            changed = True
        if not obj.mission:
            obj.mission = mission
            changed = True
        if not obj.vision:
            obj.vision = vision
            changed = True
        if changed:
            obj.save()
    else:
        AboutContent.objects.create(
            title=title,
            summary=summary,
            aim=aim,
            mission=mission,
            vision=vision,
        )


def unseed_about(apps, schema_editor):
    # Keep content if present; do not delete user edits
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0015_about_content'),
    ]

    operations = [
        migrations.RunPython(seed_about, unseed_about),
    ]