from django import template
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from functools import lru_cache

register = template.Library()


@lru_cache(maxsize=512)
def _resolve_user_for_author(name: str = "", mail: str = ""):
    """Find a matching User for a publication author.

    Priority:
    1) Match by email if provided (case-insensitive).
    2) Match by username exactly (case-insensitive) against the author name.
    3) Match by first_name + last_name exactly (case-insensitive) split on spaces.

    Returns: User or None.
    """
    name = (name or "").strip()
    mail = (mail or "").strip()

    if mail:
        u = User.objects.filter(email__iexact=mail).only("username").first()
        if u:
            return u

    if name:
        # Exact username match (case-insensitive)
        u = User.objects.filter(username__iexact=name).only("username").first()
        if u:
            return u

        # Try first_name + last_name exact match (case-insensitive)
        parts = [p for p in name.split() if p]
        if len(parts) >= 2:
            first = parts[0]
            last = parts[-1]
            u = (
                User.objects.filter(first_name__iexact=first, last_name__iexact=last)
                .only("username")
                .first()
            )
            if u:
                return u

    return None


@register.simple_tag
def author_link(name: str = "", mail: str = ""):
    """Render an author name as a link to their public profile if a match exists.

    Usage in templates:
        {% author_link a.name a.mail %}

    Falls back to plain escaped text when no matching user is found.
    """
    user = _resolve_user_for_author(name, mail)
    safe_name = escape(name or "")
    if user:
        url = reverse("profile_public", args=[user.username])
        return mark_safe(f'<a href="{url}" class="author-link">{safe_name}</a>')
    return mark_safe(safe_name)