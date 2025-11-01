from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from lab.models import Publication, PublicationAuthor, PublicationImage, PublicationContribution, CoauthorSyncRequest
from lab.models import UserProfile


class Command(BaseCommand):
    help = (
        "Scan publications' authors by email and create pending co-author sync requests "
        "for matched users who don't already have the same Work Title.\n"
        "Optionally auto-accept to clone publications immediately."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--auto-accept",
            action="store_true",
            help="Auto-accept and clone publications for matched users instead of creating pending requests.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="When a target already has a publication with the same title, update it by adding missing contributions from the source.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without making any changes.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N publications (useful for large datasets).",
        )

    def handle(self, *args, **options):
        auto_accept = options.get("auto_accept", False)
        update_existing = options.get("update_existing", False)
        dry_run = options.get("dry_run", False)
        limit = options.get("limit")

        pubs_qs = (
            Publication.objects
            .all()
            .select_related("user")
            .prefetch_related("authors", "images", "contributions")
            .order_by("id")
        )
        if limit:
            pubs_qs = pubs_qs[:limit]

        created_requests = 0
        auto_accepted = 0
        skipped_existing_pub = 0
        updated_existing_pub = 0
        skipped_self = 0
        total_matches = 0

        for p in pubs_qs:
            authors = list(p.authors.all())
            for a in authors:
                email = (a.mail or "").strip()
                if not email:
                    continue
                # Case-insensitive email match for co-author account lookup
                target = User.objects.filter(email__iexact=email).first()
                if not target:
                    continue
                total_matches += 1

                # Skip self
                if target.id == p.user_id:
                    skipped_self += 1
                    continue

                # Dedup by exact title for target user; optionally update existing with contributions
                # Case-insensitive title match to avoid duplicated requests/clones
                existing_qs = Publication.objects.filter(user=target, title__iexact=p.title)
                if existing_qs.exists():
                    if update_existing:
                        if dry_run:
                            self.stdout.write(
                                f"[DRY-RUN] UPDATE-EXISTING: add missing contributions for '{p.title}' -> {target.username}"
                            )
                        else:
                            for clone in existing_qs:
                                src_texts = {c.text for c in p.contributions.all()}
                                tgt_texts = {c.text for c in clone.contributions.all()}
                                missing = src_texts - tgt_texts
                                for txt in missing:
                                    PublicationContribution.objects.create(publication=clone, text=txt)
                            updated_existing_pub += 1
                        continue
                    else:
                        skipped_existing_pub += 1
                        continue

                if dry_run:
                    action = "CLONE" if auto_accept else "REQUEST"
                    self.stdout.write(
                        f"[DRY-RUN] {action}: '{p.title}' from {p.user.username} -> {target.username}"
                    )
                    continue

                if auto_accept:
                    # Clone publication and its authors/images to target
                    with transaction.atomic():
                        new_pub = Publication.objects.create(
                            user=target,
                            work_type=p.work_type,
                            title=p.title,
                            abstract=p.abstract,
                            conference_title=p.conference_title,
                            journal_title=p.journal_title,
                            book_title=p.book_title,
                            publication_year=p.publication_year,
                            link_paper=p.link_paper,
                            bibtex=p.bibtex,
                            github_link=p.github_link,
                            research_area=p.research_area,
                        )
                        # Preserve author sequences
                        for auth in authors:
                            PublicationAuthor.objects.create(
                                publication=new_pub,
                                name=auth.name,
                                mail=auth.mail,
                                sequence=getattr(auth, "sequence", 0),
                            )
                        for img in p.images.all():
                            PublicationImage.objects.create(publication=new_pub, image=img.image)
                        # Copy key contributions
                        for c in p.contributions.all():
                            PublicationContribution.objects.create(publication=new_pub, text=c.text)
                        # Visibility rule: only show if a PI email is among authors
                        pi_emails = {
                            (u.user.email or "").strip().lower()
                            for u in UserProfile.objects.select_related("user").filter(role="principal_investigator")
                            if (u.user.email or "").strip()
                        }
                        if pi_emails:
                            author_emails = {
                                (a.mail or "").strip().lower() for a in new_pub.authors.all() if (a.mail or "").strip()
                            }
                            new_pub.show_on_public_pages = any(e in pi_emails for e in author_emails)
                            new_pub.save(update_fields=["show_on_public_pages"])

                        CoauthorSyncRequest.objects.get_or_create(
                            source_publication=p,
                            requested_by=p.user,
                            target_user=target,
                            defaults={"status": "accepted"},
                        )
                    auto_accepted += 1
                else:
                    CoauthorSyncRequest.objects.get_or_create(
                        source_publication=p,
                        requested_by=p.user,
                        target_user=target,
                        defaults={"status": "pending"},
                    )
                    created_requests += 1

        self.stdout.write("=== Resync Summary ===")
        self.stdout.write(f"Publications processed: {pubs_qs.count()}")
        self.stdout.write(f"Author email matches: {total_matches}")
        self.stdout.write(f"Pending requests created: {created_requests}")
        self.stdout.write(f"Auto-accepted and cloned: {auto_accepted}")
        self.stdout.write(f"Skipped (already has pub): {skipped_existing_pub}")
        self.stdout.write(f"Updated existing (added contributions): {updated_existing_pub}")
        self.stdout.write(f"Skipped (self matches): {skipped_self}")
        if dry_run:
            self.stdout.write("(Dry-run mode; no changes made)")