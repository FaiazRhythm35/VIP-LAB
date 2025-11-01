from django.db import models
from django.contrib.auth.models import User


class Role(models.Model):
    """Dynamic roles for profiles, managed via admin panel.
    key: internal identifier (stable), e.g., 'graduate_student'
    name: display label, e.g., 'Graduate Student'
    display_order: optional ordering for menus
    """
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return self.name

class ResearchArea(models.Model):
    """Dynamic research areas for publications and site content.
    key: internal identifier (stable), e.g., 'computer_vision'
    name: display label, e.g., 'Computer Vision'
    summary: short text for home and listings
    details: long text for detail page
    image: hero/thumbnail image for home section
    display_order: ordering on home/research pages
    """
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    summary = models.TextField(blank=True)
    details = models.TextField(blank=True)
    image = models.ImageField(upload_to='research_areas/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return self.name

class AboutContent(models.Model):
    """Editable About page content managed from the admin panel.
    Stores a single record containing the homepage summary and detailed sections.
    """
    title = models.CharField(max_length=200, default="Visual Image Processing Lab (VIP Lab)")
    summary = models.TextField(blank=True)
    aim = models.TextField(blank=True)
    mission = models.TextField(blank=True)
    vision = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "About Content"
        verbose_name_plural = "About Content"

    def __str__(self):
        return self.title or "About Content"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.CharField(max_length=200)
    department = models.CharField(max_length=200)
    # Keep role as a string key for backward compatibility; dynamic list comes from Role
    role = models.CharField(max_length=64)
    # Extended profile fields
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    affiliation = models.CharField(max_length=255, blank=True)
    bibliography = models.TextField(blank=True)
    professional_summary = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    google_scholar_url = models.URLField(blank=True)
    research_gate_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    orcid_url = models.URLField(blank=True)
    cv_pdf = models.FileField(upload_to='cv/', blank=True, null=True)
    # Admin and ordering
    must_change_password = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    # Explicit selection flags for homepage slider
    selected_alumni = models.BooleanField(default=False)
    selected_graduate_student = models.BooleanField(default=False)

    def __str__(self):
        try:
            from .models import Role as _Role
            r = _Role.objects.filter(key=self.role).first()
            role_name = r.name if r else self.role.replace('_', ' ').title()
        except Exception:
            role_name = self.role.replace('_', ' ').title()
        return f"{self.user.get_full_name() or self.user.username} ({role_name})"

    def get_role_display(self):
        try:
            r = Role.objects.filter(key=self.role).first()
            return r.name if r else self.role.replace('_', ' ').title()
        except Exception:
            return self.role.replace('_', ' ').title()

class Interest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interests')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}"

class EducationEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='education_entries')
    name = models.CharField(max_length=200)
    institute = models.CharField(max_length=200)
    years = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.name} at {self.institute} ({self.years})"

class Publication(models.Model):
    WORK_TYPES = [
        ('journal_article', 'Journal Article'),
        ('book', 'Book'),
        ('book_chapter', 'Book Chapter'),
        ('conference_paper', 'Conference Paper'),
        ('conference_presentation', 'Conference Presentation'),
        ('conference_poster', 'Conference Poster'),
        ('preprint', 'Preprint'),
        ('dissertation_thesis', 'Dissertation or Thesis'),
        ('working_paper', 'Working Paper'),
        ('other', 'Other'),
    ]
    # Legacy static research areas (kept for reference; dynamic model now used)
    RESEARCH_AREAS = [
        ('computer_vision', 'Computer Vision'),
        ('medical_image_analysis', 'Medical Image Analysis'),
        ('remote_sensing', 'Remote Sensing'),
        ('computational_biology_bioinformatics', 'Computational Biology and Bioinformatics'),
        ('image_processing', 'Image Processing'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publications')
    work_type = models.CharField(max_length=40, choices=WORK_TYPES)
    title = models.CharField(max_length=300)
    abstract = models.TextField(blank=True)
    conference_title = models.CharField(max_length=255, blank=True)
    journal_title = models.CharField(max_length=255, blank=True)
    book_title = models.CharField(max_length=255, blank=True)
    publication_year = models.IntegerField()
    link_paper = models.URLField(blank=True)
    bibtex = models.TextField(blank=True)
    github_link = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Now dynamic: allow any key corresponding to ResearchArea.key
    research_area = models.CharField(max_length=64, blank=True)
    # New multi-select research areas (preferred going forward)
    research_areas = models.ManyToManyField(ResearchArea, related_name='publications', blank=True)
    # Ordering for admin sequencing
    display_order = models.PositiveIntegerField(default=0)
    # Visibility on aggregated public pages (Publications, Research). Kept on profiles.
    show_on_public_pages = models.BooleanField(default=True)
    # Mark as ongoing research (exclude from Publications page listing)
    is_ongoing = models.BooleanField(default=False)
    # Optional objective/goal text
    objective = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.title} ({self.publication_year})"

class PublicationAuthor(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='authors')
    name = models.CharField(max_length=200)
    mail = models.EmailField(blank=True)
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sequence', 'id']

class PublicationImage(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='publications/')

class PublicationContribution(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='contributions')
    text = models.CharField(max_length=300)

class Achievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements')
    year = models.CharField(max_length=20)
    description = models.TextField()

    def __str__(self):
        return f"{self.year}: {self.description[:40]}"

class Experience(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='experiences')
    years = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    institute = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=[('work', 'Work'), ('affiliation', 'Professional Affiliation')], default='work')
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True, default="")
    link = models.URLField(blank=True)

    def __str__(self):
        return f"{self.title} at {self.institute} ({self.years})"

class ExperiencePoint(models.Model):
    experience = models.ForeignKey(Experience, on_delete=models.CASCADE, related_name='points')
    text = models.CharField(max_length=300)

class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    year = models.CharField(max_length=10)
    title = models.CharField(max_length=200)
    institute = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True, default="")
    github_link = models.URLField(blank=True)

    def __str__(self):
        return f"{self.title} ({self.year})"

class ProjectPoint(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='points')
    text = models.CharField(max_length=300)

class ProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='projects/')

class CoauthorSyncRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    source_publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='sync_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_sync_requests')
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coauthor_sync_requests')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('source_publication', 'target_user')

    def __str__(self):
        return f"Sync '{self.source_publication.title}' to {self.target_user.username} ({self.status})"


class NewsItem(models.Model):
    text = models.TextField()
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', '-id']

    def __str__(self):
        return self.text[:60]


class LabAward(models.Model):
    text = models.TextField()
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='awards/', blank=True, null=True)

    class Meta:
        ordering = ['display_order', '-id']

    def __str__(self):
        return self.text[:60]
