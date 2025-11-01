from django.shortcuts import render, redirect
from django.http import Http404
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth import logout as auth_logout, update_session_auth_hash
from django.contrib.auth.models import User
import random
from django.contrib.auth.decorators import login_required
from .models import UserProfile, Role, ResearchArea, AboutContent, NewsItem, LabAward
from django.db.models import Max
from django.http import FileResponse
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse

# Create your views here.

# Legacy static AREAS removed in favor of dynamic ResearchArea model


def _new_captcha(request):
    a, b = random.randint(1, 9), random.randint(1, 9)
    request.session['captcha_answer'] = str(a + b)
    return f"{a} + {b}"


# Visibility helper: only show publications on aggregated public tabs
# when a Principal Investigator email appears among the authors.
def _get_pi_emails():
    try:
        from .models import UserProfile
    except Exception:
        return set()
    # Use the core account email for PI(s)
    profiles = (UserProfile.objects
                .select_related('user')
                .filter(role='principal_investigator'))
    emails = set()
    for p in profiles:
        e = (getattr(p.user, 'email', '') or '').strip().lower()
        if e:
            emails.add(e)
    return emails


def _recalculate_public_visibility_by_pi(pub):
    """Set Publication.show_on_public_pages based on PI authorship emails."""
    try:
        from .models import PublicationAuthor
        pi_emails = _get_pi_emails()
        # If no PI emails configured, keep current visibility
        if not pi_emails:
            return getattr(pub, 'show_on_public_pages', True)
        author_emails = [
            (a.mail or '').strip().lower()
            for a in PublicationAuthor.objects.filter(publication=pub)
            if getattr(a, 'mail', None)
        ]
        new_val = any(e in pi_emails for e in author_emails)
        if pub.show_on_public_pages != new_val:
            pub.show_on_public_pages = new_val
            pub.save(update_fields=['show_on_public_pages'])
        return new_val
    except Exception:
        return getattr(pub, 'show_on_public_pages', True)


def _sync_contributions_to_clones(pub):
    """Ensure co-authors' cloned publications have at least the source's contributions.
    Does not remove extras on clones; only adds missing texts.
    Matching by title + co-author email ownership.
    """
    try:
        from .models import PublicationAuthor as PAuth, PublicationContribution
        # Collect co-author user ids from author emails on the source publication
        coauthor_emails = [
            (a.mail or '').strip().lower()
            for a in PAuth.objects.filter(publication=pub)
            if getattr(a, 'mail', None)
        ]
        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
        if not coauthor_ids:
            return
        clones = list(
            Publication.objects
            .filter(user_id__in=coauthor_ids, title__iexact=pub.title)
            .exclude(id=pub.id)
        )
        if not clones:
            return
        src_texts = { (c.text or '').strip() for c in pub.contributions.all() if (c.text or '').strip() }
        if not src_texts:
            return
        for cp in clones:
            tgt_texts = { (c.text or '').strip() for c in cp.contributions.all() if (c.text or '').strip() }
            missing = src_texts - tgt_texts
            for txt in missing:
                PublicationContribution.objects.create(publication=cp, text=txt)
    except Exception:
        # Best-effort helper; swallow errors
        pass


def home(request):
    from .models import UserProfile, Publication
    profiles_qs = (UserProfile.objects
                   .select_related('user')
                   .prefetch_related('user__interests')
                   .filter(user__is_superuser=False))
    about = AboutContent.objects.first()
    # Build combined team list: PI, Assistant PI, RAs, selected Grad Students, selected Alumni
    pi = list(profiles_qs.filter(role='principal_investigator').order_by('display_order','user__id'))
    asst = list(profiles_qs.filter(role='assistant_pi').order_by('display_order','user__id'))
    ras = list(profiles_qs.filter(role='research_assistant').order_by('display_order','user__id'))
    selected_grads = list(profiles_qs.filter(role='graduate_student', selected_graduate_student=True).order_by('display_order','user__id'))
    selected_alumni = list(profiles_qs.filter(role='alumni', selected_alumni=True).order_by('display_order','user__id'))
    team_profiles = pi + asst + ras + selected_grads + selected_alumni

    # Attach role labels for display convenience
    role_labels = {r.key: r.name for r in Role.objects.order_by('display_order','id')}
    for p in team_profiles:
        setattr(p, 'role_label', role_labels.get(p.role, p.role.replace('_',' ').title()))

    # Ongoing research projects (latest few across all areas)
    try:
        from django.db.models import Q
        pi_emails = list(_get_pi_emails())
        ongoing_qs = (
            Publication.objects
            .filter(show_on_public_pages=True, is_ongoing=True)
            .select_related('user')
            .prefetch_related('authors')
            .order_by('-publication_year', 'display_order', '-id')
        )
        if pi_emails:
            ongoing_qs = ongoing_qs.filter(
                Q(authors__mail__in=pi_emails) | Q(user__email__in=pi_emails)
            ).distinct()
        # Dedupe by title and prefer a canonical copy using simple heuristics
        by_title = {}
        def score(pub):
            s = 0
            try:
                prof = getattr(pub.user, 'profile', None)
                if getattr(prof, 'role', None) == 'principal_investigator':
                    s += 1000
            except Exception:
                pass
            if getattr(pub, 'abstract', ''):
                s += 100
            if getattr(pub, 'objective', ''):
                s += 50
            if getattr(pub, 'link_paper', ''):
                s += 10
            if getattr(pub, 'bibtex', ''):
                s += 10
            try:
                s += int(getattr(pub, 'publication_year', 0) or 0)
            except Exception:
                pass
            return s
        for p in ongoing_qs:
            t = (p.title or '').strip()
            if t not in by_title:
                by_title[t] = p
            else:
                cur = by_title[t]
                sc_new = score(p)
                sc_cur = score(cur)
                if sc_new > sc_cur or (sc_new == sc_cur and p.id > cur.id):
                    by_title[t] = p
        home_ongoing_projects = list(by_title.values())[:5]
    except Exception:
        home_ongoing_projects = []

    context = {
        # Dynamic Research Areas for home page grid
        'areas': ResearchArea.objects.order_by('display_order', 'id'),
        'team_profiles': team_profiles,
        'about_summary': getattr(about, 'summary', ''),
        'about_title': getattr(about, 'title', 'About'),
        'home_news': NewsItem.objects.filter(is_active=True).order_by('display_order','-id'),
        'home_awards': LabAward.objects.filter(is_active=True).order_by('display_order','-id'),
        'home_ongoing_projects': home_ongoing_projects,
    }
    return render(request, 'lab/home.html', context)


def research_detail(request, slug):
    # Map hyphenated slug to underscore key used in Publication.research_area
    key = (slug or '').replace('-', '_')
    ra = ResearchArea.objects.filter(key=key).first()
    if not ra:
        raise Http404("Area not found")
    area_ctx = {
        'title': ra.name,
        'summary': ra.summary,
        'details': ra.details,
    }
    return render(request, 'lab/research_detail.html', {'area': area_ctx, 'slug': slug})


def login(request):
    context = {}
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        captcha = request.POST.get('captcha', '').strip()
        expected = request.session.get('captcha_answer')
        if not expected or captcha != expected:
            messages.error(request, 'Captcha verification failed. Please try again.')
            context['captcha_question'] = _new_captcha(request)
            context['role_choices'] = {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
            return render(request, 'lab/login.html', context)
        user = None
        if email:
            user = User.objects.filter(email=email).first()
        if user:
            user = authenticate(request, username=user.username, password=password)
        if not user:
            messages.error(request, 'Invalid email or password.')
            context['captcha_question'] = _new_captcha(request)
            context['role_choices'] = {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
            return render(request, 'lab/login.html', context)
        # Prevent login for inactive accounts (pending admin approval)
        if not user.is_active:
            messages.error(request, 'Your account is pending admin approval. Please wait until an admin activates your account.')
            context['captcha_question'] = _new_captcha(request)
            context['role_choices'] = {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
            return render(request, 'lab/login.html', context)
        auth_login(request, user)
        messages.success(request, 'Logged in successfully.')
        return redirect('home')
    else:
        context['captcha_question'] = _new_captcha(request)
        context['role_choices'] = {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
    return render(request, 'lab/login.html', context)


def forgot_password(request):
    context = {}
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        captcha = request.POST.get('captcha', '').strip()
        expected = request.session.get('captcha_answer')
        if not expected or captcha != expected:
            messages.error(request, 'Captcha verification failed. Please try again.')
            context['captcha_question'] = _new_captcha(request)
            return render(request, 'lab/forgot_password.html', context)
        user = None
        if email:
            user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, 'No account found with that email.')
            context['captcha_question'] = _new_captcha(request)
            return render(request, 'lab/forgot_password.html', context)
        # Generate reset link
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = request.build_absolute_uri(
            reverse('reset_password', kwargs={'uidb64': uid, 'token': token})
        )
        subject = 'Reset your password — VIP Research Lab'
        message = (
            'You requested a password reset.\n\n'
            f'Click the link below to set a new password:\n{reset_url}\n\n'
            'If you did not request this, you can ignore this email.'
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
            messages.success(request, 'Password reset link sent to your email.')
            return redirect('login')
        except Exception as e:
            messages.error(request, f'Failed to send reset email: {e}')
            context['captcha_question'] = _new_captcha(request)
            return render(request, 'lab/forgot_password.html', context)
    else:
        context['captcha_question'] = _new_captcha(request)
    return render(request, 'lab/forgot_password.html', context)


def reset_password(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except Exception:
        user = None
    if not user or not default_token_generator.check_token(user, token):
        messages.error(request, 'Reset link is invalid or expired.')
        return redirect('forgot_password')
    if request.method == 'POST':
        new = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        captcha = request.POST.get('captcha', '').strip()
        expected = request.session.get('captcha_answer')
        if not expected or captcha != expected:
            messages.error(request, 'Captcha verification failed. Please try again.')
            return render(request, 'lab/reset_password.html', {'uidb64': uidb64, 'token': token, 'captcha_question': _new_captcha(request)})
        if not new or len(new) < 8:
            messages.error(request, 'Please choose a password with at least 8 characters.')
            return render(request, 'lab/reset_password.html', {'uidb64': uidb64, 'token': token, 'captcha_question': _new_captcha(request)})
        if new != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'lab/reset_password.html', {'uidb64': uidb64, 'token': token, 'captcha_question': _new_captcha(request)})
        user.set_password(new)
        user.save()
        messages.success(request, 'Your password has been reset. You can now log in.')
        return redirect('login')
    return render(request, 'lab/reset_password.html', {'uidb64': uidb64, 'token': token, 'captcha_question': _new_captcha(request)})


def signup(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm_password', '')
        organization = request.POST.get('organization', '').strip()
        department = request.POST.get('department', '').strip()
        role = request.POST.get('role', '').strip()
        # Bot protections
        robot_check = request.POST.get('i_am_not_robot')
        honey = request.POST.get('contact_phone', '').strip()

        errors = []
        # Honeypot and checkbox validations
        if honey:
            errors.append('Bot-like activity detected.')
        if not robot_check:
            errors.append('Please confirm you are not a robot.')

        # Field validations
        if not all([name, email, password, confirm, organization, department, role]):
            errors.append('Please fill in all required fields.')
        # Simple email validation without regex
        if email and ('@' not in email or '.' not in email.split('@')[-1]):
            errors.append('Valid email is required.')
        if password and len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if User.objects.filter(email=email).exists():
            errors.append('An account with this email already exists.')

        # Validate role against dynamic Role list
        if role and not Role.objects.filter(key=role).exists():
            errors.append('Please select a valid role.')

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'lab/login.html', {
                'captcha_question': _new_captcha(request),
                'show_signup': True,
                'role_choices': {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
            })

        # Ensure username uniqueness
        username = email.split('@')[0]
        base_username = username
        n = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{n}"
            n += 1

        user = User.objects.create_user(username=username, email=email, password=password)
        # Set inactive until admin approval
        user.is_active = False
        # Split name into first and last if possible
        parts = name.split()
        if parts:
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = ' '.join(parts[1:])
        # Persist changes (name + inactive status)
        user.save()

        UserProfile.objects.create(user=user, organization=organization, department=department, role=role)

        # Retroactive Publication Sync: auto-add past publications where new user's email
        # appears in existing publications' author list.
        try:
            from django.db import transaction
            from .models import Publication, PublicationAuthor, PublicationImage, PublicationContribution
            new_email = (email or '').strip()
            if new_email:
                author_qs = (
                    PublicationAuthor.objects
                    .filter(mail__iexact=new_email)
                    .select_related('publication', 'publication__user')
                    .prefetch_related('publication__authors', 'publication__images')
                )
                seen_pub_ids = set()
                cloned_count = 0
                for auth in author_qs:
                    sp = auth.publication
                    if sp.id in seen_pub_ids:
                        continue
                    seen_pub_ids.add(sp.id)
                    # Skip if source publication already belongs to the new user
                    if sp.user_id == user.id:
                        continue
                    # Dedup: skip if new user already has a publication with the same title
                    if Publication.objects.filter(user=user, title=sp.title).exists():
                        continue
                    # Clone publication, authors (with sequence), images, and contributions
                    with transaction.atomic():
                        new_p = Publication.objects.create(
                            user=user,
                            work_type=sp.work_type,
                            title=sp.title,
                            abstract=sp.abstract,
                            conference_title=sp.conference_title,
                            journal_title=sp.journal_title,
                            book_title=sp.book_title,
                            publication_year=sp.publication_year,
                            link_paper=sp.link_paper,
                            bibtex=sp.bibtex,
                            github_link=sp.github_link,
                            research_area=sp.research_area,
                            objective=getattr(sp, 'objective', ''),
                            is_ongoing=getattr(sp, 'is_ongoing', False),
                        )
                        # Copy M2M areas when available
                        try:
                            new_p.research_areas.set(sp.research_areas.all())
                        except Exception:
                            pass
                        for a in sp.authors.all():
                            PublicationAuthor.objects.create(
                                publication=new_p,
                                name=a.name,
                                mail=a.mail,
                                sequence=getattr(a, 'sequence', 0),
                            )
                        for img in sp.images.all():
                            PublicationImage.objects.create(publication=new_p, image=img.image)
                        # Copy key contributions
                        try:
                            for c in getattr(sp, 'contributions', []).all():
                                PublicationContribution.objects.create(publication=new_p, text=c.text)
                        except Exception:
                            pass
                        # Recalculate visibility for cloned publication
                        _recalculate_public_visibility_by_pi(new_p)
                        cloned_count += 1
                if cloned_count:
                    messages.success(request, f'Found and added {cloned_count} past publications to your profile.')
        except Exception as e:
            messages.warning(request, f'Retroactive sync encountered an issue: {e}')

        messages.success(request, 'Registration successful. Your account is pending admin approval. You will be able to log in after approval.')
        return redirect('login')

    return render(request, 'lab/login.html', {
        'captcha_question': _new_captcha(request),
        'show_signup': True,
        'role_choices': {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
    })


def search(request):
    query = request.GET.get('q') or request.POST.get('q')
    results = []
    if query:
        q = query.strip()
        areas = ResearchArea.objects.all()
        if q:
            from django.db.models import Q
            areas = areas.filter(
                Q(name__icontains=q) | Q(summary__icontains=q) | Q(details__icontains=q)
            )
        for ra in areas.order_by('display_order', 'id'):
            results.append({
                'slug': ra.key.replace('_', '-'),
                'title': ra.name,
                'summary': ra.summary,
            })
    context = {'query': query, 'results': results}
    return render(request, 'lab/search.html', context)


def people(request):
    profiles = (UserProfile.objects
                .select_related('user')
                .prefetch_related('user__achievements','user__education_entries','user__publications','user__experiences','user__projects','user__interests')
                .filter(user__is_superuser=False))
    roles = Role.objects.order_by('display_order', 'id')
    sections = []
    for r in roles:
        qs = profiles.filter(role=r.key).order_by('display_order','user__id')
        anchor_id = f"role-{r.key}".replace('_', '-')
        sections.append({
            'key': r.key,
            'label': r.name,
            'anchor_id': anchor_id,
            'profiles': qs,
        })
    return render(request, 'lab/people.html', {'role_sections': sections})

def about(request):
    obj = AboutContent.objects.first()
    ctx = {
        'title': getattr(obj, 'title', 'About'),
        'summary': getattr(obj, 'summary', ''),
        'aim': getattr(obj, 'aim', ''),
        'mission': getattr(obj, 'mission', ''),
        'vision': getattr(obj, 'vision', ''),
    }
    return render(request, 'lab/about.html', ctx)

@login_required
def admin_users(request):
    if not request.user.is_superuser:
        messages.error(request, 'Admin access required.')
        return redirect('home')
    from .models import UserProfile
    users = UserProfile.objects.select_related('user').filter(user__is_superuser=False)
    # Apply GET filters for better UX
    q = (request.GET.get('q') or '').strip()
    role_filter = (request.GET.get('role') or '').strip()
    status_filter = (request.GET.get('status') or '').strip()
    if q:
        from django.db.models import Q
        users = users.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__email__icontains=q)
        )
    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == 'active':
        users = users.filter(user__is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(user__is_active=False)
    users = users.order_by('display_order', 'user__id')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_user':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            password = request.POST.get('password', '').strip()
            role = request.POST.get('role', 'graduate_student').strip()
            organization = request.POST.get('organization', '').strip()
            department = request.POST.get('department', '').strip()
            errors = []
            if not email or '@' not in email:
                errors.append('Valid email required.')
            if not password or len(password) < 8:
                errors.append('Password must be at least 8 characters.')
            if role and not Role.objects.filter(key=role).exists():
                errors.append('Please select a valid role.')
            if User.objects.filter(email=email).exists():
                errors.append('A user with this email already exists.')
            if errors:
                for e in errors:
                    messages.error(request, e)
            else:
                username = email.split('@')[0]
                base_username = username
                n = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{n}"
                    n += 1
                user = User.objects.create_user(username=username, email=email, password=password)
                parts = (name or '').split()
                if parts:
                    user.first_name = parts[0]
                    user.last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
                    user.save()
                max_order = UserProfile.objects.filter(role=role).aggregate(Max('display_order'))['display_order__max'] or 0
                UserProfile.objects.create(user=user, organization=organization, department=department, role=role, display_order=max_order + 1)
                messages.success(request, 'User created.')
                return redirect('admin_users')
        elif action == 'add_role':
            key = request.POST.get('role_key', '').strip()
            name = request.POST.get('role_name', '').strip()
            order_val = request.POST.get('role_order', '').strip()
            errs = []
            if not key:
                errs.append('Role key is required.')
            if not name:
                errs.append('Role name is required.')
            if key and Role.objects.filter(key=key).exists():
                errs.append('Role key must be unique.')
            try:
                order = int(order_val) if order_val else 0
            except Exception:
                order = 0
            if errs:
                for e in errs:
                    messages.error(request, e)
            else:
                Role.objects.create(key=key, name=name, display_order=order)
                messages.success(request, 'Role added.')
            return redirect('admin_users')
        elif action == 'edit_role':
            role_id = request.POST.get('role_id')
            new_name = request.POST.get('role_name', '').strip()
            new_order_val = request.POST.get('role_order', '').strip()
            try:
                r = Role.objects.get(id=int(role_id))
            except Exception:
                r = None
            if not r:
                messages.error(request, 'Role not found.')
                return redirect('admin_users')
            if not new_name:
                messages.error(request, 'Role name cannot be empty.')
                return redirect('admin_users')
            try:
                new_order = int(new_order_val) if new_order_val else r.display_order
            except Exception:
                new_order = r.display_order
            r.name = new_name
            r.display_order = new_order
            r.save(update_fields=['name', 'display_order'])
            messages.success(request, 'Role updated.')
            return redirect('admin_users')
        elif action == 'delete_role':
            role_id = request.POST.get('role_id')
            try:
                r = Role.objects.get(id=int(role_id))
            except Exception:
                r = None
            if not r:
                messages.error(request, 'Role not found.')
                return redirect('admin_users')
            # Prevent deleting a role that is currently in use by any profile
            usage_count = UserProfile.objects.filter(role=r.key).count()
            if usage_count > 0:
                messages.error(request, f'Cannot delete role "{r.name}" because it is assigned to {usage_count} user(s). Reassign those users first.')
                return redirect('admin_users')
            r.delete()
            messages.success(request, 'Role deleted.')
            return redirect('admin_users')
        elif action == 'add_area':
            key = request.POST.get('area_key', '').strip()
            name = request.POST.get('area_name', '').strip()
            summary = request.POST.get('area_summary', '').strip()
            details = request.POST.get('area_details', '').strip()
            order_val = request.POST.get('area_order', '').strip()
            image = request.FILES.get('area_image')
            errs = []
            if not key:
                errs.append('Research area key is required.')
            if not name:
                errs.append('Research area name is required.')
            if key and ResearchArea.objects.filter(key=key).exists():
                errs.append('Research area key must be unique.')
            try:
                order = int(order_val) if order_val else 0
            except Exception:
                order = 0
            if errs:
                for e in errs:
                    messages.error(request, e)
            else:
                ra = ResearchArea.objects.create(
                    key=key, name=name, summary=summary, details=details, display_order=order
                )
                if image:
                    ra.image = image
                    ra.save(update_fields=['image'])
                messages.success(request, 'Research area added.')
            return redirect('admin_users')
        elif action == 'edit_area':
            area_id = request.POST.get('area_id')
            name = request.POST.get('area_name', '').strip()
            summary = request.POST.get('area_summary', '').strip()
            details = request.POST.get('area_details', '').strip()
            order_val = request.POST.get('area_order', '').strip()
            image = request.FILES.get('area_image')
            ra = ResearchArea.objects.filter(id=area_id).first()
            if not ra:
                messages.error(request, 'Research area not found.')
                return redirect('admin_users')
            if not name:
                messages.error(request, 'Research area name cannot be empty.')
                return redirect('admin_users')
            try:
                order = int(order_val) if order_val else ra.display_order
            except Exception:
                order = ra.display_order
            ra.name = name
            ra.summary = summary
            ra.details = details
            ra.display_order = order
            if image:
                ra.image = image
            ra.save()
            messages.success(request, 'Research area updated.')
            return redirect('admin_users')
        elif action == 'delete_area':
            from .models import Publication
            area_id = request.POST.get('area_id')
            ra = ResearchArea.objects.filter(id=area_id).first()
            if not ra:
                messages.error(request, 'Research area not found.')
                return redirect('admin_users')
            # Safety check: prevent deletion if any publication uses this area
            m2m_count = Publication.objects.filter(research_areas=ra).count()
            legacy_count = Publication.objects.filter(research_area=ra.key).count()
            usage_count = m2m_count + legacy_count
            if usage_count:
                messages.error(request, f'Cannot delete research area "{ra.name}" because it is used by {usage_count} publication(s). Reassign or remove them first.')
                return redirect('admin_users')
            ra.delete()
            messages.success(request, 'Research area deleted.')
            return redirect('admin_users')
        elif action == 'delete_user':
            uid = request.POST.get('user_id')
            try:
                u = User.objects.get(id=uid)
            except User.DoesNotExist:
                u = None
            if u:
                if u.is_superuser:
                    messages.error(request, 'Cannot delete the Super Admin account.')
                else:
                    u.delete()
                    messages.success(request, 'User deleted.')
                return redirect('admin_users')
            else:
                messages.error(request, 'User not found.')
        elif action == 'activate_all_pending':
            # Bulk-approve all pending non-superuser accounts
            updated = User.objects.filter(is_superuser=False, is_active=False).update(is_active=True)
            messages.success(request, f'Approved {updated} pending user(s).')
            return redirect('admin_users')
        elif action == 'activate_user':
            uid = request.POST.get('user_id')
            try:
                u = User.objects.get(id=uid)
            except User.DoesNotExist:
                u = None
            if not u:
                messages.error(request, 'User not found.')
                return redirect('admin_users')
            if u.is_superuser:
                messages.error(request, 'Cannot change the Super Admin active status.')
                return redirect('admin_users')
            u.is_active = True
            u.save(update_fields=['is_active'])
            messages.success(request, 'User approved and activated.')
            return redirect('admin_users')
        elif action == 'deactivate_user':
            uid = request.POST.get('user_id')
            try:
                u = User.objects.get(id=uid)
            except User.DoesNotExist:
                u = None
            if not u:
                messages.error(request, 'User not found.')
                return redirect('admin_users')
            if u.is_superuser:
                messages.error(request, 'Cannot change the Super Admin active status.')
                return redirect('admin_users')
            if u == request.user:
                messages.error(request, 'You cannot deactivate your own admin account.')
                return redirect('admin_users')
            u.is_active = False
            u.save(update_fields=['is_active'])
            messages.success(request, 'User deactivated.')
            return redirect('admin_users')
        elif action == 'update_admin_email':
            new_email = request.POST.get('email', '').strip().lower()
            errors = []
            if not new_email or '@' not in new_email:
                errors.append('Valid email required.')
            elif User.objects.filter(email__iexact=new_email).exclude(pk=request.user.pk).exists():
                errors.append('A user with this email already exists.')
            if errors:
                for e in errors:
                    messages.error(request, e)
            else:
                request.user.email = new_email
                request.user.save(update_fields=['email'])
                messages.success(request, 'Admin email updated.')
            return redirect('admin_users')
        elif action == 'update_admin_password':
            current = request.POST.get('current_password', '')
            new1 = request.POST.get('new_password', '')
            new2 = request.POST.get('confirm_password', '')
            if not request.user.check_password(current):
                messages.error(request, 'Current password is incorrect.')
            elif len(new1) < 8:
                messages.error(request, 'New password must be at least 8 characters.')
            elif new1 != new2:
                messages.error(request, 'New passwords do not match.')
            else:
                request.user.set_password(new1)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                profile = getattr(request.user, 'profile', None)
                if profile:
                    profile.must_change_password = False
                    profile.save(update_fields=['must_change_password'])
                messages.success(request, 'Admin password changed successfully.')
            return redirect('admin_users')
        elif action == 'add_news':
            text = request.POST.get('news_text', '').strip()
            order_val = request.POST.get('news_order', '').strip()
            try:
                order = int(order_val) if order_val else 0
            except Exception:
                order = 0
            if not text:
                messages.error(request, 'News text cannot be empty.')
            else:
                NewsItem.objects.create(text=text, display_order=order, is_active=True)
                messages.success(request, 'News item added.')
            return redirect('admin_users')
        elif action == 'delete_news':
            nid = request.POST.get('news_id')
            NewsItem.objects.filter(id=nid).delete()
            messages.success(request, 'News item deleted.')
            return redirect('admin_users')
        elif action == 'update_news_order':
            nid = request.POST.get('news_id')
            order_val = request.POST.get('news_order', '').strip()
            n = NewsItem.objects.filter(id=nid).first()
            if not n:
                messages.error(request, 'News item not found.')
                return redirect('admin_users')
            try:
                new_order = int(order_val)
            except Exception:
                new_order = n.display_order
            n.display_order = new_order
            n.save(update_fields=['display_order'])
            messages.success(request, 'News order updated.')
            return redirect('admin_users')
        elif action == 'add_award':
            text = request.POST.get('award_text', '').strip()
            order_val = request.POST.get('award_order', '').strip()
            image = request.FILES.get('award_image')
            try:
                order = int(order_val) if order_val else 0
            except Exception:
                order = 0
            if not text:
                messages.error(request, 'Award text cannot be empty.')
            else:
                LabAward.objects.create(text=text, display_order=order, is_active=True, image=image)
                messages.success(request, 'Award/Achievement added.')
            return redirect('admin_users')
        elif action == 'update_award_image':
            aid = request.POST.get('award_id')
            image = request.FILES.get('award_image')
            if not image:
                messages.error(request, 'Please choose an image to upload.')
                return redirect('admin_users')
            aw = LabAward.objects.filter(id=aid).first()
            if not aw:
                messages.error(request, 'Award not found.')
            else:
                aw.image = image
                aw.save(update_fields=['image'])
                messages.success(request, 'Award image updated.')
            return redirect('admin_users')
        elif action == 'delete_award':
            aid = request.POST.get('award_id')
            LabAward.objects.filter(id=aid).delete()
            messages.success(request, 'Award/Achievement deleted.')
            return redirect('admin_users')
        elif action == 'update_award_order':
            aid = request.POST.get('award_id')
            order_val = request.POST.get('award_order', '').strip()
            aw = LabAward.objects.filter(id=aid).first()
            if not aw:
                messages.error(request, 'Award not found.')
                return redirect('admin_users')
            try:
                new_order = int(order_val)
            except Exception:
                new_order = aw.display_order
            aw.display_order = new_order
            aw.save(update_fields=['display_order'])
            messages.success(request, 'Award order updated.')
            return redirect('admin_users')
        elif action == 'update_about':
            title = request.POST.get('about_title', '').strip()
            summary = request.POST.get('about_summary', '').strip()
            aim = request.POST.get('about_aim', '').strip()
            mission = request.POST.get('about_mission', '').strip()
            vision = request.POST.get('about_vision', '').strip()
            obj, _ = AboutContent.objects.get_or_create(id=1)
            if title:
                obj.title = title
            obj.summary = summary
            obj.aim = aim
            obj.mission = mission
            obj.vision = vision
            obj.save()
            messages.success(request, 'About content updated.')
            return redirect('admin_users')
    return render(request, 'lab/admin_users.html', {
        'profiles': users,
        'role_choices': {r.key: r.name for r in Role.objects.order_by('display_order', 'id')},
        'roles': Role.objects.order_by('display_order', 'id'),
        'areas': ResearchArea.objects.order_by('display_order', 'id'),
        'about': AboutContent.objects.first(),
        'admin_news': NewsItem.objects.order_by('display_order','-id'),
        'admin_awards': LabAward.objects.order_by('display_order','-id'),
    })
@login_required
def user_profile(request):
    current_user = request.user
    target_user = current_user
    is_admin_editing = False
    # Allow superuser to edit another user's profile via query param ?user_id=
    if getattr(current_user, 'is_superuser', False):
        user_id = request.GET.get('user_id')
        if user_id and str(user_id).isdigit():
            try:
                candidate = User.objects.get(id=int(user_id))
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                return redirect('admin_users')
            if candidate.is_superuser:
                messages.error(request, 'Cannot edit the Super Admin profile here.')
                return redirect('admin_users')
            target_user = candidate
            is_admin_editing = True
        else:
            # Super Admin without target user: go back to admin panel
            return redirect('admin_users')
    # Use target user for the rest of the handler
    user = target_user
    from .models import (
        UserProfile, Interest, EducationEntry,
        Publication, PublicationAuthor, PublicationImage,
        Achievement, Experience, ExperiencePoint,
        Project, ProjectPoint, ProjectImage,
        CoauthorSyncRequest,
    )

    # Ensure profile exists
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'organization': getattr(getattr(user, 'profile', None), 'organization', '') or '',
            'department': getattr(getattr(user, 'profile', None), 'department', '') or '',
            'role': getattr(getattr(user, 'profile', None), 'role', 'graduate_student') or 'graduate_student',
        },
    )

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        try:
            if form_type == 'update_profile':
                if 'profile_picture' in request.FILES:
                    profile.profile_picture = request.FILES['profile_picture']
                profile.affiliation = request.POST.get('affiliation', '')
                profile.bibliography = request.POST.get('bibliography', '')
                # Professional Summary with hard 100-word limit
                summary = (request.POST.get('professional_summary', '') or '').strip()
                invalid_summary = False
                if summary:
                    words = summary.split()
                    if len(words) > 100:
                        messages.error(request, 'Professional Summary must be at most 100 words.')
                        invalid_summary = True
                # Assign to instance so form re-renders with typed value even if invalid
                profile.professional_summary = summary
                # Contact email: sync to auth user.email for login
                new_email = request.POST.get('contact_email', '').strip().lower()
                profile.contact_email = new_email
                if new_email:
                    # Basic validity check and uniqueness
                    if ('@' in new_email and '.' in new_email.split('@')[-1]):
                        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                            messages.error(request, 'This email is already in use by another account.')
                        else:
                            user.email = new_email
                    else:
                        messages.error(request, 'Please provide a valid email address.')
                profile.google_scholar_url = request.POST.get('google_scholar_url', '')
                profile.research_gate_url = request.POST.get('research_gate_url', '')
                profile.github_url = request.POST.get('github_url', '')
                profile.orcid_url = request.POST.get('orcid_url', '')
                # Signup info
                profile.organization = request.POST.get('organization', '').strip()
                profile.department = request.POST.get('department', '').strip()
                role = request.POST.get('role', '').strip()
                if role:
                    if Role.objects.filter(key=role).exists():
                        profile.role = role
                    else:
                        messages.error(request, 'Please select a valid role.')
                # Admin-only homepage highlight flags
                if request.user.is_superuser:
                    profile.selected_alumni = bool(request.POST.get('selected_alumni'))
                    profile.selected_graduate_student = bool(request.POST.get('selected_graduate_student'))
                # Name info
                user.first_name = request.POST.get('first_name', '').strip()
                user.last_name = request.POST.get('last_name', '').strip()
                if not invalid_summary:
                    user.save()
                    profile.save()
                    messages.success(request, 'Profile updated.')
            elif form_type == 'change_password':
                current = request.POST.get('current_password', '')
                new1 = request.POST.get('new_password', '')
                new2 = request.POST.get('confirm_password', '')
                if not user.check_password(current):
                    messages.error(request, 'Current password is incorrect.')
                elif len(new1) < 8:
                    messages.error(request, 'New password must be at least 8 characters.')
                elif new1 != new2:
                    messages.error(request, 'New passwords do not match.')
                else:
                    from django.contrib.auth import update_session_auth_hash
                    user.set_password(new1)
                    user.save()
                    profile.must_change_password = False
                    profile.save(update_fields=['must_change_password'])
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Password changed successfully.')
            elif form_type == 'upload_cv':
                if 'cv_pdf' in request.FILES:
                    profile.cv_pdf = request.FILES['cv_pdf']
                    profile.save()
                    messages.success(request, 'CV uploaded.')
                else:
                    messages.error(request, 'Please select a PDF to upload.')
            elif form_type == 'change_password':
                current = request.POST.get('current_password', '')
                new = request.POST.get('new_password', '')
                confirm = request.POST.get('confirm_password', '')
                if not user.check_password(current):
                    messages.error(request, 'Current password is incorrect.')
                elif not new or len(new) < 6:
                    messages.error(request, 'New password must be at least 6 characters.')
                elif new != confirm:
                    messages.error(request, 'New password and confirmation do not match.')
                else:
                    user.set_password(new)
                    user.save()
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Password updated.')
            elif form_type == 'add_interest':
                name = request.POST.get('interest_name', '').strip()
                if name:
                    Interest.objects.create(user=user, name=name)
                    messages.success(request, 'Interest added.')
                else:
                    messages.error(request, 'Interest name is required.')
            elif form_type == 'delete_interest':
                iid = request.POST.get('interest_id')
                Interest.objects.filter(id=iid, user=user).delete()
                messages.success(request, 'Interest deleted.')
            elif form_type == 'add_education':
                name = request.POST.get('name', '').strip()
                institute = request.POST.get('institute', '').strip()
                years = request.POST.get('years', '').strip()
                if name and institute and years:
                    EducationEntry.objects.create(user=user, name=name, institute=institute, years=years)
                    messages.success(request, 'Education entry added.')
                else:
                    messages.error(request, 'All education fields are required.')
            elif form_type == 'delete_education':
                eid = request.POST.get('education_id')
                EducationEntry.objects.filter(id=eid, user=user).delete()
                messages.success(request, 'Education entry deleted.')
            elif form_type == 'add_publication':
                work_type = request.POST.get('work_type')
                title = request.POST.get('title', '').strip()
                abstract = request.POST.get('abstract', '')
                conference_title = request.POST.get('conference_title', '')
                journal_title = request.POST.get('journal_title', '')
                book_title = request.POST.get('book_title', '')
                year = request.POST.get('publication_year')
                link_paper = request.POST.get('link_paper', '').strip()
                bibtex = request.POST.get('bibtex', '')
                github_link = request.POST.get('github_link', '').strip()
                # New: objective, ongoing, and multi-area selection
                objective = request.POST.get('objective', '').strip()
                is_ongoing = bool(request.POST.get('is_ongoing'))
                selected_area_keys = [k for k in request.POST.getlist('research_areas') if k]
                legacy_area = (selected_area_keys[0] if selected_area_keys else request.POST.get('research_area', ''))
                if title and year and work_type:
                    p = Publication.objects.create(
                        user=user,
                        work_type=work_type,
                        title=title,
                        abstract=abstract,
                        conference_title=conference_title,
                        journal_title=journal_title,
                        book_title=book_title,
                        publication_year=int(year),
                        link_paper=link_paper,
                        bibtex=bibtex,
                        github_link=github_link,
                        research_area=legacy_area,
                        objective=objective,
                        is_ongoing=is_ongoing,
                    )
                    # Assign M2M research areas if provided
                    if selected_area_keys:
                        areas = list(ResearchArea.objects.filter(key__in=selected_area_keys))
                        if areas:
                            p.research_areas.set(areas)
                    # Authors (multiple)
                    author_names = [n.strip() for n in request.POST.getlist('author_name')]
                    author_mails = [m.strip() for m in request.POST.getlist('author_mail')]
                    pairs = [(n, (author_mails[i] if i < len(author_mails) else '')) for i, n in enumerate(author_names) if n]
                    for idx, (n, m) in enumerate(pairs, start=1):
                        PublicationAuthor.objects.create(publication=p, name=n, mail=m, sequence=idx)
                    # Enforce PI authorship visibility rule after authors are saved
                    vis = _recalculate_public_visibility_by_pi(p)
                    if not vis:
                        messages.info(request, 'Publication will not appear on Publications/Research tabs because no Principal Investigator email is among the authors.')
                    # Seed contributions from textarea (one per line)
                    contrib_blob = request.POST.get('key_contributions', '')
                    if contrib_blob:
                        from .models import PublicationContribution
                        for line in [ln.strip() for ln in contrib_blob.splitlines()]:
                            if line:
                                PublicationContribution.objects.create(publication=p, text=line)
                    # Images (multiple)
                    for f in request.FILES.getlist('images'):
                        PublicationImage.objects.create(publication=p, image=f)

                    # Co-author sync requests (confirmation workflow)
                    # For each author mail matching a registered user (not User A),
                    # create a pending sync request if User B does not already have this title.
                    from .models import CoauthorSyncRequest
                    processed = set()
                    for _, m in pairs:
                        if not m:
                            continue
                        # Case-insensitive email match to find co-author accounts
                        match = User.objects.filter(email__iexact=m).first()
                        if match and match.id != user.id:
                            if match.id in processed:
                                continue
                            processed.add(match.id)
                            # Avoid duplicating requests when target already has this title (case-insensitive)
                            if not Publication.objects.filter(user=match, title__iexact=p.title).exists():
                                # Use update_or_create so previously rejected/accepted pairs can be resent
                                CoauthorSyncRequest.objects.update_or_create(
                                    source_publication=p,
                                    target_user=match,
                                    defaults={"requested_by": user, "status": "pending"},
                                )

                    messages.success(request, 'Publication added. Co-author sync requests created for matched users.')
                else:
                    messages.error(request, 'Work type, title, and year are required.')
            elif form_type == 'delete_publication':
                pid = request.POST.get('publication_id')
                Publication.objects.filter(id=pid, user=user).delete()
                messages.success(request, 'Publication deleted.')
            elif form_type == 'add_publication_author':
                pid = request.POST.get('publication_id')
                name = request.POST.get('name', '').strip()
                mail = request.POST.get('mail', '').strip()
                p = Publication.objects.filter(id=pid, user=user).first()
                if p and name:
                    max_seq = PublicationAuthor.objects.filter(publication=p).aggregate(Max('sequence'))['sequence__max'] or 0
                    new_seq = (max_seq + 1)
                    PublicationAuthor.objects.create(publication=p, name=name, mail=mail, sequence=new_seq)
                    # Recalculate public visibility based on PI authorship
                    vis = _recalculate_public_visibility_by_pi(p)
                    if not vis:
                        messages.info(request, 'Publication remains hidden on Publications/Research tabs because no PI email is among the authors.')
                    # If the added author mail maps to a registered user (not self) and
                    # they don't already have this title, queue a pending co-author sync request
                    try:
                        if mail:
                            from .models import CoauthorSyncRequest
                            target = User.objects.filter(email__iexact=mail).first()
                            if target and target.id != user.id:
                                if not Publication.objects.filter(user=target, title__iexact=p.title).exists():
                                    CoauthorSyncRequest.objects.update_or_create(
                                        source_publication=p,
                                        target_user=target,
                                        defaults={"requested_by": user, "status": "pending"},
                                    )
                    except Exception:
                        # Best-effort; do not block author add
                        pass
                    # Propagate new author to co-authors' cloned publications
                    try:
                        from .models import PublicationAuthor as PAuth
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PAuth.objects.filter(publication=p)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=p.title)
                                .exclude(id=p.id)
                            )
                            for c in clones:
                                exists = PAuth.objects.filter(publication=c, name=name, mail=mail).exists()
                                if not exists:
                                    PAuth.objects.create(publication=c, name=name, mail=mail, sequence=new_seq)
                                # Recalculate visibility for each clone
                                _recalculate_public_visibility_by_pi(c)
                    except Exception:
                        pass
                    messages.success(request, 'Author added.')
                else:
                    messages.error(request, 'Author name is required.')
            elif form_type == 'delete_publication_author':
                aid = request.POST.get('author_id')
                # After deletion, recalc visibility for the affected publication if possible
                try:
                    auth = PublicationAuthor.objects.select_related('publication').filter(id=aid, publication__user=user).first()
                    pub = getattr(auth, 'publication', None)
                except Exception:
                    auth = None
                    pub = None
                # Capture values for propagation
                old_name = getattr(auth, 'name', '')
                old_mail = getattr(auth, 'mail', '')
                PublicationAuthor.objects.filter(id=aid, publication__user=user).delete()
                if pub:
                    vis = _recalculate_public_visibility_by_pi(pub)
                    if not vis:
                        messages.info(request, 'Publication is hidden on Publications/Research tabs because no PI email is among the authors.')
                    # Propagate deletion to co-authors' cloned publications
                    try:
                        from .models import PublicationAuthor as PAuth
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PAuth.objects.filter(publication=pub)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=pub.title)
                                .exclude(id=pub.id)
                            )
                            for c in clones:
                                PublicationAuthor.objects.filter(publication=c, name=old_name, mail=old_mail).delete()
                                _recalculate_public_visibility_by_pi(c)
                    except Exception:
                        pass
                messages.success(request, 'Author deleted.')
            elif form_type == 'add_publication_contribution':
                from .models import PublicationContribution
                pid = request.POST.get('publication_id')
                text = request.POST.get('text', '').strip()
                p = Publication.objects.filter(id=pid, user=user).first()
                if p and text:
                    PublicationContribution.objects.create(publication=p, text=text)
                    # Propagate to co-authors' cloned publications
                    try:
                        from .models import PublicationAuthor
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PublicationAuthor.objects.filter(publication=p)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=p.title)
                                .exclude(id=p.id)
                            )
                            for c in clones:
                                # Add only if missing to avoid duplicates
                                exists = c.contributions.filter(text=text).exists()
                                if not exists:
                                    PublicationContribution.objects.create(publication=c, text=text)
                            # Ensure any other source contributions are mirrored
                            _sync_contributions_to_clones(p)
                    except Exception:
                        # Best-effort; do not block user action
                        pass
                    messages.success(request, 'Contribution added.')
                else:
                    messages.error(request, 'Contribution text is required.')
            elif form_type == 'edit_publication_contribution':
                from .models import PublicationContribution
                cid = request.POST.get('contribution_id')
                text = request.POST.get('text', '').strip()
                c = PublicationContribution.objects.filter(id=cid, publication__user=user).first()
                if c and text:
                    old_text = c.text
                    c.text = text
                    c.save(update_fields=['text'])
                    # Propagate edit to co-authors' cloned publications
                    try:
                        p = c.publication
                        from .models import PublicationAuthor
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PublicationAuthor.objects.filter(publication=p)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=p.title)
                                .exclude(id=p.id)
                            )
                            for cp in clones:
                                # Update matching text if present; otherwise add new
                                tc = cp.contributions.filter(text=old_text).first()
                                if tc:
                                    tc.text = text
                                    tc.save(update_fields=['text'])
                                else:
                                    if not cp.contributions.filter(text=text).exists():
                                        PublicationContribution.objects.create(publication=cp, text=text)
                            # Ensure any other source contributions are mirrored
                            _sync_contributions_to_clones(p)
                    except Exception:
                        pass
                    messages.success(request, 'Contribution updated.')
                else:
                    messages.error(request, 'Contribution not found or text empty.')
            elif form_type == 'delete_publication_contribution':
                from .models import PublicationContribution
                cid = request.POST.get('contribution_id')
                # Fetch to capture text and publication before delete
                c = PublicationContribution.objects.select_related('publication').filter(id=cid, publication__user=user).first()
                if c:
                    p = c.publication
                    del_text = c.text
                    PublicationContribution.objects.filter(id=cid, publication__user=user).delete()
                    # Propagate deletion to clones
                    try:
                        from .models import PublicationAuthor
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PublicationAuthor.objects.filter(publication=p)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=p.title)
                                .exclude(id=p.id)
                            )
                            for cp in clones:
                                # Delete only one matching contribution to avoid removing duplicates
                                tc = cp.contributions.filter(text=del_text).first()
                                if tc:
                                    tc.delete()
                            # Resync to ensure clones mirror source set after deletion
                            _sync_contributions_to_clones(p)
                    except Exception:
                        pass
                else:
                    # Fallback: attempt direct delete
                    PublicationContribution.objects.filter(id=cid, publication__user=user).delete()
                messages.success(request, 'Contribution deleted.')
            elif form_type == 'add_publication_image':
                pid = request.POST.get('publication_id')
                p = Publication.objects.filter(id=pid, user=user).first()
                if p:
                    created_imgs = []
                    for f in request.FILES.getlist('images'):
                        img = PublicationImage.objects.create(publication=p, image=f)
                        created_imgs.append(img)
                    # Propagate new images to co-authors' cloned publications
                    try:
                        from .models import PublicationAuthor as PAuth
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PAuth.objects.filter(publication=p)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids and created_imgs:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=p.title)
                                .exclude(id=p.id)
                            )
                            for c in clones:
                                for img in created_imgs:
                                    # Avoid duplicates: check if an image with same file exists
                                    exists = PublicationImage.objects.filter(publication=c, image=img.image.name).exists()
                                    if not exists:
                                        PublicationImage.objects.create(publication=c, image=img.image)
                    except Exception:
                        pass
                    messages.success(request, 'Publication images uploaded.')
                else:
                    messages.error(request, 'Publication not found.')
            elif form_type == 'delete_publication_image':
                iid = request.POST.get('publication_image_id')
                # Fetch image to capture file path before deletion
                img = PublicationImage.objects.select_related('publication').filter(id=iid, publication__user=user).first()
                if img:
                    p = img.publication
                    img_path = img.image.name
                    PublicationImage.objects.filter(id=iid, publication__user=user).delete()
                    # Propagate deletion to co-authors' cloned publications
                    try:
                        from .models import PublicationAuthor as PAuth
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PAuth.objects.filter(publication=p)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids and img_path:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=p.title)
                                .exclude(id=p.id)
                            )
                            for c in clones:
                                PublicationImage.objects.filter(publication=c, image=img_path).delete()
                    except Exception:
                        pass
                else:
                    PublicationImage.objects.filter(id=iid, publication__user=user).delete()
                messages.success(request, 'Publication image deleted.')
            elif form_type == 'add_achievement':
                year = request.POST.get('year', '').strip()
                desc = request.POST.get('description', '').strip()
                if year and desc:
                    Achievement.objects.create(user=user, year=year, description=desc)
                    messages.success(request, 'Achievement added.')
                else:
                    messages.error(request, 'Year and description are required.')
            elif form_type == 'delete_achievement':
                aid = request.POST.get('achievement_id')
                Achievement.objects.filter(id=aid, user=user).delete()
                messages.success(request, 'Achievement deleted.')
            elif form_type == 'add_experience':
                years = request.POST.get('years', '').strip()
                title = request.POST.get('title', '').strip()
                institute = request.POST.get('institute', '').strip()
                link = request.POST.get('link', '').strip()
                category = request.POST.get('category', 'work').strip()
                key_point = request.POST.get('key_point', '').strip()
                if years and title and institute:
                    ex = Experience.objects.create(
                        user=user,
                        years=years,
                        title=title,
                        institute=institute,
                        link=link,
                        category=(category if category in ['work', 'affiliation'] else 'work')
                    )
                    if key_point:
                        ExperiencePoint.objects.create(experience=ex, text=key_point)
                    messages.success(request, 'Experience added.')
                else:
                    messages.error(request, 'Years, title, and institute are required.')
            elif form_type == 'delete_experience':
                xid = request.POST.get('experience_id')
                Experience.objects.filter(id=xid, user=user).delete()
                messages.success(request, 'Experience deleted.')
            elif form_type == 'add_experience_point':
                xid = request.POST.get('experience_id')
                text = request.POST.get('text', '').strip()
                ex = Experience.objects.filter(id=xid, user=user).first()
                if ex and text:
                    ExperiencePoint.objects.create(experience=ex, text=text)
                    messages.success(request, 'Experience point added.')
                else:
                    messages.error(request, 'Point text is required.')
            elif form_type == 'delete_experience_point':
                pid = request.POST.get('point_id')
                ExperiencePoint.objects.filter(id=pid, experience__user=user).delete()
                messages.success(request, 'Experience point deleted.')
            elif form_type == 'add_project':
                year = request.POST.get('year', '').strip()
                title = request.POST.get('title', '').strip()
                institute = request.POST.get('institute', '').strip()
                github_link = request.POST.get('github_link', '').strip()
                key_point = request.POST.get('key_point', '').strip()
                if year and title:
                    pr = Project.objects.create(user=user, year=year, title=title, institute=institute, github_link=github_link)
                    if key_point:
                        ProjectPoint.objects.create(project=pr, text=key_point)
                    messages.success(request, 'Project added.')
                else:
                    messages.error(request, 'Year and title are required.')
            elif form_type == 'delete_project':
                pid = request.POST.get('project_id')
                Project.objects.filter(id=pid, user=user).delete()
                messages.success(request, 'Project deleted.')
            elif form_type == 'add_project_point':
                pid = request.POST.get('project_id')
                text = request.POST.get('text', '').strip()
                pr = Project.objects.filter(id=pid, user=user).first()
                if pr and text:
                    ProjectPoint.objects.create(project=pr, text=text)
                    messages.success(request, 'Project point added.')
                else:
                    messages.error(request, 'Point text is required.')
            elif form_type == 'delete_project_point':
                ptid = request.POST.get('point_id')
                ProjectPoint.objects.filter(id=ptid, project__user=user).delete()
                messages.success(request, 'Project point deleted.')
            elif form_type == 'add_project_image':
                pid = request.POST.get('project_id')
                pr = Project.objects.filter(id=pid, user=user).first()
                if pr:
                    for f in request.FILES.getlist('images'):
                        ProjectImage.objects.create(project=pr, image=f)
                    messages.success(request, 'Project images uploaded.')
                else:
                    messages.error(request, 'Project not found.')
            elif form_type == 'delete_project_image':
                iid = request.POST.get('project_image_id')
                ProjectImage.objects.filter(id=iid, project__user=user).delete()
                messages.success(request, 'Project image deleted.')
            # EDIT ACTIONS
            elif form_type == 'edit_interest':
                iid = request.POST.get('interest_id')
                name = request.POST.get('interest_name', '').strip()
                it = Interest.objects.filter(id=iid, user=user).first()
                if it and name:
                    it.name = name
                    it.save()
                    messages.success(request, 'Interest updated.')
                else:
                    messages.error(request, 'Interest not found or name empty.')
            elif form_type == 'edit_education':
                eid = request.POST.get('education_id')
                name = request.POST.get('name', '').strip()
                institute = request.POST.get('institute', '').strip()
                years = request.POST.get('years', '').strip()
                ed = EducationEntry.objects.filter(id=eid, user=user).first()
                if ed and name and institute and years:
                    ed.name = name
                    ed.institute = institute
                    ed.years = years
                    ed.save()
                    messages.success(request, 'Education entry updated.')
                else:
                    messages.error(request, 'Education entry not found or fields missing.')
            elif form_type == 'edit_publication':
                pid = request.POST.get('publication_id')
                pub = Publication.objects.filter(id=pid, user=user).first()
                if pub:
                    # Keep original identifiers so we can find co-author clones reliably
                    old_title = pub.title
                    old_year = pub.publication_year
                    pub.work_type = request.POST.get('work_type', pub.work_type)
                    pub.title = request.POST.get('title', pub.title).strip()
                    pub.abstract = request.POST.get('abstract', pub.abstract)
                    pub.conference_title = request.POST.get('conference_title', pub.conference_title)
                    pub.journal_title = request.POST.get('journal_title', pub.journal_title)
                    pub.book_title = request.POST.get('book_title', pub.book_title)
                    try:
                        pub.publication_year = int(request.POST.get('publication_year', pub.publication_year))
                    except (TypeError, ValueError):
                        pass
                    pub.link_paper = request.POST.get('link_paper', pub.link_paper)
                    pub.bibtex = request.POST.get('bibtex', pub.bibtex)
                    pub.github_link = request.POST.get('github_link', pub.github_link)
                    # New fields
                    pub.objective = request.POST.get('objective', pub.objective)
                    pub.is_ongoing = bool(request.POST.get('is_ongoing'))
                    # Multi-area selection
                    selected_area_keys = [k for k in request.POST.getlist('research_areas') if k]
                    if selected_area_keys:
                        ras = list(ResearchArea.objects.filter(key__in=selected_area_keys))
                        pub.research_areas.set(ras)
                        pub.research_area = selected_area_keys[0]
                    else:
                        # Allow clearing
                        pub.research_areas.clear()
                        pub.research_area = request.POST.get('research_area', pub.research_area)
                    pub.save()
                    # Propagate updates to co-authors' copies when their email matches a user
                    try:
                        from .models import PublicationAuthor
                        # Collect co-author emails from this publication
                        coauthor_emails = [
                            a.mail.lower() for a in PublicationAuthor.objects.filter(publication=pub)
                            if getattr(a, 'mail', None)
                        ]
                        if coauthor_emails:
                            coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True))
                        else:
                            coauthor_ids = []

                        if coauthor_ids:
                            update_fields = {
                                'work_type': pub.work_type,
                                'title': pub.title,
                                'abstract': pub.abstract,
                                'conference_title': pub.conference_title,
                                'journal_title': pub.journal_title,
                                'book_title': pub.book_title,
                                'publication_year': pub.publication_year,
                                'link_paper': pub.link_paper,
                                'bibtex': pub.bibtex,
                                'github_link': pub.github_link,
                                'research_area': pub.research_area,
                                'objective': getattr(pub, 'objective', ''),
                                'is_ongoing': getattr(pub, 'is_ongoing', False),
                            }
                            base_clones_qs = (
                                Publication.objects
                                .filter(user_id__in=coauthor_ids)
                                .exclude(id=pub.id)
                            )
                            clones_old = list(base_clones_qs.filter(title__iexact=old_title))
                            clones_new = list(base_clones_qs.filter(title__iexact=pub.title))
                            # Merge without duplicates
                            seen = {}
                            for c in clones_old + clones_new:
                                seen[c.id] = c
                            clones = list(seen.values())
                            for c in clones:
                                for k, v in update_fields.items():
                                    setattr(c, k, v)
                                c.save()
                                try:
                                    c.research_areas.set(pub.research_areas.all())
                                except Exception:
                                    pass
                                # Sync contributions: add any missing from source
                                try:
                                    from .models import PublicationContribution
                                    src_texts = {cc.text for cc in pub.contributions.all()}
                                    tgt_texts = {cc.text for cc in c.contributions.all()}
                                    missing = src_texts - tgt_texts
                                    for txt in missing:
                                        PublicationContribution.objects.create(publication=c, text=txt)
                                except Exception:
                                    pass
                    except Exception:
                        # Non-fatal: propagation is best-effort
                        pass
                    messages.success(request, 'Publication updated.')
                else:
                    messages.error(request, 'Publication not found.')
            elif form_type == 'edit_publication_author':
                aid = request.POST.get('author_id')
                name = request.POST.get('name', '').strip()
                mail = request.POST.get('mail', '').strip()
                auth = PublicationAuthor.objects.filter(id=aid, publication__user=user).first()
                if auth and name:
                    # Capture old values for propagation
                    old_name = auth.name
                    old_mail = auth.mail
                    auth.name = name
                    auth.mail = mail
                    auth.save()
                    # If the edited author now has a mail that maps to a registered user (not self)
                    # and they don't already have this title, queue a pending co-author sync request
                    try:
                        pub = auth.publication
                        if mail:
                            from .models import CoauthorSyncRequest
                            target = User.objects.filter(email__iexact=mail).first()
                            if target and target.id != user.id:
                                if not Publication.objects.filter(user=target, title__iexact=pub.title).exists():
                                    CoauthorSyncRequest.objects.update_or_create(
                                        source_publication=pub,
                                        target_user=target,
                                        defaults={"requested_by": user, "status": "pending"},
                                    )
                    except Exception:
                        # Non-fatal: continue with propagation
                        pass
                    # Propagate edit to co-authors' cloned publications
                    try:
                        pub = auth.publication
                        from .models import PublicationAuthor as PAuth
                        coauthor_emails = [
                            (a.mail or '').strip().lower()
                            for a in PAuth.objects.filter(publication=pub)
                            if getattr(a, 'mail', None)
                        ]
                        coauthor_ids = list(User.objects.filter(email__in=coauthor_emails).values_list('id', flat=True)) if coauthor_emails else []
                        if coauthor_ids:
                            clones = list(
                                Publication.objects
                                .filter(user_id__in=coauthor_ids, title__iexact=pub.title)
                                .exclude(id=pub.id)
                            )
                            for c in clones:
                                ta = PAuth.objects.filter(publication=c, name=old_name, mail=old_mail).first()
                                if ta:
                                    ta.name = name
                                    ta.mail = mail
                                    ta.save()
                                else:
                                    # If not present, add new author with same sequence
                                    PAuth.objects.create(publication=c, name=name, mail=mail, sequence=getattr(auth, 'sequence', 0))
                                _recalculate_public_visibility_by_pi(c)
                    except Exception:
                        pass
                    messages.success(request, 'Author updated.')
                else:
                    messages.error(request, 'Author not found or name empty.')
            elif form_type == 'edit_achievement':
                aid = request.POST.get('achievement_id')
                year = request.POST.get('year', '').strip()
                description = request.POST.get('description', '').strip()
                ach = Achievement.objects.filter(id=aid, user=user).first()
                if ach and year and description:
                    ach.year = year
                    ach.description = description
                    ach.save()
                    messages.success(request, 'Achievement updated.')
                else:
                    messages.error(request, 'Achievement not found or fields missing.')
            elif form_type == 'edit_experience':
                xid = request.POST.get('experience_id')
                years = request.POST.get('years', '').strip()
                title = request.POST.get('title', '').strip()
                institute = request.POST.get('institute', '').strip()
                link = request.POST.get('link', '').strip()
                ex = Experience.objects.filter(id=xid, user=user).first()
                if ex and years and title and institute:
                    ex.years = years
                    ex.title = title
                    ex.institute = institute
                    ex.link = link
                    ex.save()
                    messages.success(request, 'Experience updated.')
                else:
                    messages.error(request, 'Experience not found or required fields missing.')
            elif form_type == 'edit_experience_point':
                pid = request.POST.get('point_id')
                text = request.POST.get('text', '').strip()
                pt = ExperiencePoint.objects.filter(id=pid, experience__user=user).first()
                if pt and text:
                    pt.text = text
                    pt.save()
                    messages.success(request, 'Experience point updated.')
                else:
                    messages.error(request, 'Point not found or text empty.')
            elif form_type == 'edit_project':
                pid = request.POST.get('project_id')
                year = request.POST.get('year', '').strip()
                title = request.POST.get('title', '').strip()
                institute = request.POST.get('institute', '').strip()
                github_link = request.POST.get('github_link', '').strip()
                pr = Project.objects.filter(id=pid, user=user).first()
                if pr and year and title:
                    pr.year = year
                    pr.title = title
                    pr.institute = institute
                    pr.github_link = github_link
                    pr.save()
                    messages.success(request, 'Project updated.')
                else:
                    messages.error(request, 'Project not found or required fields missing.')
            elif form_type == 'edit_project_point':
                ptid = request.POST.get('point_id')
                text = request.POST.get('text', '').strip()
                ppt = ProjectPoint.objects.filter(id=ptid, project__user=user).first()
                if ppt and text:
                    ppt.text = text
                    ppt.save()
                    messages.success(request, 'Project point updated.')
                else:
                    messages.error(request, 'Point not found or text empty.')
            elif form_type == 'move_publication_author_up':
                aid = request.POST.get('author_id')
                auth = PublicationAuthor.objects.filter(id=aid, publication__user=user).select_related('publication').first()
                if auth:
                    prev = PublicationAuthor.objects.filter(publication=auth.publication, sequence__lt=auth.sequence).order_by('-sequence').first()
                    if prev:
                        auth.sequence, prev.sequence = prev.sequence, auth.sequence
                        auth.save(update_fields=['sequence'])
                        prev.save(update_fields=['sequence'])
                        messages.success(request, 'Author moved up.')
                    else:
                        messages.info(request, 'Author is already first.')
                else:
                    messages.error(request, 'Author not found.')
            elif form_type == 'move_publication_author_down':
                aid = request.POST.get('author_id')
                auth = PublicationAuthor.objects.filter(id=aid, publication__user=user).select_related('publication').first()
                if auth:
                    nxt = PublicationAuthor.objects.filter(publication=auth.publication, sequence__gt=auth.sequence).order_by('sequence').first()
                    if nxt:
                        auth.sequence, nxt.sequence = nxt.sequence, auth.sequence
                        auth.save(update_fields=['sequence'])
                        nxt.save(update_fields=['sequence'])
                        messages.success(request, 'Author moved down.')
                    else:
                        messages.info(request, 'Author is already last.')
                else:
                    messages.error(request, 'Author not found.')
            elif form_type == 'accept_coauthor_sync':
                rid = request.POST.get('request_id')
                req = CoauthorSyncRequest.objects.filter(id=rid, target_user=user, status='pending').select_related('source_publication', 'requested_by').first()
                if req:
                    sp = req.source_publication
                    # Case-insensitive check to prevent duplicate clones when casing differs
                    if not Publication.objects.filter(user=user, title__iexact=sp.title).exists():
                        new_p = Publication.objects.create(
                            user=user,
                            work_type=sp.work_type,
                            title=sp.title,
                            abstract=sp.abstract,
                            conference_title=sp.conference_title,
                            journal_title=sp.journal_title,
                            book_title=sp.book_title,
                            publication_year=sp.publication_year,
                            link_paper=sp.link_paper,
                            bibtex=sp.bibtex,
                            github_link=sp.github_link,
                            research_area=sp.research_area,
                            objective=getattr(sp, 'objective', ''),
                            is_ongoing=getattr(sp, 'is_ongoing', False),
                        )
                        try:
                            new_p.research_areas.set(sp.research_areas.all())
                        except Exception:
                            pass
                        for a in sp.authors.all():
                            PublicationAuthor.objects.create(publication=new_p, name=a.name, mail=a.mail, sequence=a.sequence)
                        for img in sp.images.all():
                            PublicationImage.objects.create(publication=new_p, image=img.image)
                        # Copy key contributions
                        try:
                            from .models import PublicationContribution
                            for c in sp.contributions.all():
                                PublicationContribution.objects.create(publication=new_p, text=c.text)
                        except Exception:
                            pass
                        _recalculate_public_visibility_by_pi(new_p)
                    req.status = 'accepted'
                    req.save(update_fields=['status'])
                    messages.success(request, 'Co-author sync accepted and publication cloned to your profile.')
                else:
                    messages.error(request, 'Sync request not found or already processed.')
            elif form_type == 'reject_coauthor_sync':
                rid = request.POST.get('request_id')
                req = CoauthorSyncRequest.objects.filter(id=rid, target_user=user, status='pending').first()
                if req:
                    req.status = 'rejected'
                    req.save(update_fields=['status'])
                    messages.info(request, 'Co-author sync request rejected.')
                else:
                    messages.error(request, 'Sync request not found or already processed.')
            else:
                messages.error(request, 'Unknown action.')
        except Exception as e:
            messages.error(request, f'Error: {e}')
        return redirect('user_profile')

    interests = Interest.objects.filter(user=user).order_by('name')
    education_entries = EducationEntry.objects.filter(user=user).order_by('-id')
    publications = Publication.objects.filter(user=user).prefetch_related('authors','images').order_by('-created_at')
    achievements = Achievement.objects.filter(user=user).order_by('-id')
    experiences = Experience.objects.filter(user=user).prefetch_related('points').order_by('-id')
    work_experiences = Experience.objects.filter(user=user, category='work').prefetch_related('points').order_by('-id')
    affiliation_experiences = Experience.objects.filter(user=user, category='affiliation').prefetch_related('points').order_by('-id')
    projects = Project.objects.filter(user=user).prefetch_related('points','images').order_by('-id')

    pub_work_types = dict(Publication.WORK_TYPES)
    # Dynamic research areas mapping for forms
    pub_research_areas = {r.key: r.name for r in ResearchArea.objects.order_by('display_order', 'id')}

    pending_sync_requests = CoauthorSyncRequest.objects.filter(target_user=user, status='pending').select_related('source_publication','requested_by').order_by('-created_at')

    from django.urls import reverse
    context = {
        'profile': profile,
        'interests': interests,
        'education_entries': education_entries,
        'publications': publications,
        'achievements': achievements,
        'experiences': experiences,
        'work_experiences': work_experiences,
        'affiliation_experiences': affiliation_experiences,
        'projects': projects,
        'pub_work_types': pub_work_types,
        'pub_research_areas': pub_research_areas,
        'pending_sync_requests': pending_sync_requests,
        'target_user': user,
    }
    # Dynamic UI/context for admin editing
    context['is_admin_editing'] = is_admin_editing
    context['header_title'] = (
        f"Edit Profile: {user.get_full_name() or user.username}"
        if is_admin_editing else "Your Profile"
    )
    context['public_profile_url'] = reverse('profile_public', args=[user.username])
    # Ensure form posts back to the same handler with correct target
    form_action = request.path
    if is_admin_editing:
        form_action = f"{form_action}?user_id={user.id}"
    context['profile_form_action'] = form_action
    # Dynamic role choices for role select
    context['role_choices'] = {r.key: r.name for r in Role.objects.order_by('display_order', 'id')}
    return render(request, 'lab/profile.html', context)


def logout_view(request):
    auth_logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('home')


def research(request):
    from .models import UserProfile, Publication
    from django.db.models import Q, Prefetch

    # Build Projects (per-area sections) with Selected and Ongoing research projects
    pi_emails = list(_get_pi_emails())
    area_sections = []
    for ra in ResearchArea.objects.order_by('display_order', 'id'):
        key = ra.key
        base_qs = (
            Publication.objects
            .filter(research_areas=ra, show_on_public_pages=True)
            .select_related('user')
            .prefetch_related('authors', 'images', 'contributions')
            .order_by('display_order', '-publication_year', '-id')
        )
        if pi_emails:
            base_qs = base_qs.filter(
                Q(authors__mail__in=pi_emails) | Q(user__email__in=pi_emails)
            ).distinct()

        def _dedupe_by_title(qs):
            # Prefer a canonical record among duplicates (same title) using heuristics:
            # 1) PI-owned copy wins; 2) richer content (abstract/objective/contributions/images);
            # 3) presence of links; 4) more recent year; 5) higher id to break ties.
            by_title = {}
            def score(pub):
                s = 0
                try:
                    prof = getattr(pub.user, 'profile', None)
                    if getattr(prof, 'role', None) == 'principal_investigator':
                        s += 1000
                except Exception:
                    pass
                if getattr(pub, 'abstract', ''):
                    s += 100
                if getattr(pub, 'objective', ''):
                    s += 50
                try:
                    s += 20 * len(pub.contributions.all())
                except Exception:
                    pass
                try:
                    s += 5 * len(pub.images.all())
                except Exception:
                    pass
                if getattr(pub, 'link_paper', ''):
                    s += 10
                if getattr(pub, 'bibtex', ''):
                    s += 10
                try:
                    s += int(getattr(pub, 'publication_year', 0) or 0)
                except Exception:
                    pass
                return s
            for p in qs:
                t = (p.title or '').strip()
                if t not in by_title:
                    by_title[t] = p
                else:
                    current = by_title[t]
                    sc_new = score(p)
                    sc_cur = score(current)
                    if sc_new > sc_cur or (sc_new == sc_cur and p.id > current.id):
                        by_title[t] = p
            return list(by_title.values())

        selected_qs = base_qs.filter(is_ongoing=False)
        ongoing_qs = base_qs.filter(is_ongoing=True)
        area_sections.append({
            'key': key,
            'label': ra.name,
            'summary': ra.summary,
            'details': ra.details,
            'image': ra.image,
            'selected_projects': _dedupe_by_title(selected_qs),
            'ongoing_projects': _dedupe_by_title(ongoing_qs),
        })

    # Build Publications data (roles -> profiles -> publications)
    roles_qs = Role.objects.order_by('display_order', 'id')
    role_labels = {r.key: r.name for r in roles_qs}
    selected_role = request.GET.get('role', 'principal_investigator')
    selected_area = request.GET.get('area', 'all')
    sort = request.GET.get('sort') or 'order'
    selected_user_id = request.GET.get('user_id')
    role_keys = list(role_labels.keys())
    roles_to_render = role_keys if selected_role == 'all' or selected_role not in role_keys else [selected_role]
    order_fields = ['user__first_name', 'user__last_name', 'user__username'] if sort == 'name' else ['display_order', 'user__id']

    profiles_qs = (UserProfile.objects
                   .select_related('user')
                   .prefetch_related(
                       Prefetch(
                           'user__publications',
                           queryset=(
                               Publication.objects
                               .filter(show_on_public_pages=True, is_ongoing=False)
                               .order_by('-publication_year', 'display_order', '-id')
                               .prefetch_related('authors', 'images')
                           ) if not pi_emails else (
                               Publication.objects
                               .filter(show_on_public_pages=True, is_ongoing=False, authors__mail__in=pi_emails)
                               .distinct()
                               .order_by('-publication_year', 'display_order', '-id')
                               .prefetch_related('authors', 'images')
                           )
                       )
                   )
                   .filter(user__is_superuser=False))

    def _filter_by_user(qs):
        if selected_user_id and str(selected_user_id).isdigit():
            return qs.filter(user__id=int(selected_user_id))
        return qs

    pub_sections = [
        {
            'key': role,
            'label': role_labels.get(role, role.replace('_', ' ').title()),
            'profiles': _filter_by_user(profiles_qs.filter(role=role)).order_by(*order_fields),
        }
        for role in roles_to_render
    ]
    role_menu = [(r.key, r.name) for r in roles_qs]
    area_menu = [(ra.key, ra.name) for ra in ResearchArea.objects.order_by('display_order', 'id')]

    selected_tab = request.GET.get('tab') or 'publications'
    context = {
        'area_sections': area_sections,
        'pub_sections': pub_sections,
        'role_selected': selected_role,
        'area_selected': selected_area,
        'sort_selected': sort,
        'role_menu': role_menu,
        'area_menu': area_menu,
        'role_labels': role_labels,
        'selected_tab': selected_tab,
        'user_selected_id': int(selected_user_id) if selected_user_id and str(selected_user_id).isdigit() else None,
    }
    return render(request, 'lab/research.html', context)


def publications(request):
    from .models import UserProfile, Publication
    from django.db.models import Prefetch
    roles_qs = Role.objects.order_by('display_order', 'id')
    labels_map = {r.key: r.name for r in roles_qs}
    # Default filter: show Principal Investigator publications by default
    selected_role = request.GET.get('role', 'principal_investigator')
    # Research area selected from query (for initial UI state only; filtering is client-side)
    selected_area = request.GET.get('area', 'all')
    sort = request.GET.get('sort') or 'order'
    selected_user_id = request.GET.get('user_id')
    role_keys = list(labels_map.keys())
    roles_to_render = role_keys if selected_role == 'all' or selected_role not in role_keys else [selected_role]
    order_fields = ['user__first_name', 'user__last_name', 'user__username'] if sort == 'name' else ['display_order', 'user__id']

    pi_emails = list(_get_pi_emails())
    profiles_qs = (UserProfile.objects
                   .select_related('user')
                   .prefetch_related(
                       Prefetch(
                           'user__publications',
                           queryset=(
                               Publication.objects
                               .filter(show_on_public_pages=True, is_ongoing=False)
                               .order_by('-publication_year', 'display_order', '-id')
                               .prefetch_related('authors', 'images')
                           ) if not pi_emails else (
                               Publication.objects
                               .filter(show_on_public_pages=True, is_ongoing=False, authors__mail__in=pi_emails)
                               .distinct()
                               .order_by('-publication_year', 'display_order', '-id')
                               .prefetch_related('authors', 'images')
                           )
                       )
                   )
                   .filter(user__is_superuser=False))

    def _filter_by_user(qs):
        if selected_user_id and str(selected_user_id).isdigit():
            return qs.filter(user__id=int(selected_user_id))
        return qs

    sections = [
        {
            'key': role,
            'label': labels_map.get(role, role.replace('_', ' ').title()),
            'profiles': _filter_by_user(profiles_qs.filter(role=role)).order_by(*order_fields),
        }
        for role in roles_to_render
    ]
    role_menu = [(r.key, r.name) for r in roles_qs]
    area_menu = [(ra.key, ra.name) for ra in ResearchArea.objects.order_by('display_order', 'id')]
    return render(request, 'lab/publications.html', {
        'sections': sections,
        'role_selected': selected_role,
        'area_selected': selected_area,
        'sort_selected': sort,
        'role_menu': role_menu,
        'area_menu': area_menu,
        'role_labels': labels_map,
        'user_selected_id': int(selected_user_id) if selected_user_id and str(selected_user_id).isdigit() else None,
    })


def profile_public(request, username):
    from django.contrib.auth.models import User
    from django.shortcuts import get_object_or_404
    from .models import UserProfile, Publication

    user = get_object_or_404(User, username=username)
    if user.is_superuser:
        raise Http404
    # Profile may not exist; handle gracefully
    profile = getattr(user, 'profile', None)

    interests = user.interests.all()
    # Sort education entries by most recent year (end year) first
    def _edu_sort_val(s):
        import re
        if not s:
            return -1
        s = s.replace('–', '-').replace('—', '-')
        years = re.findall(r'(?:19|20)\d{2}', s)
        if years:
            return int(years[-1])
        return -1
    education_entries = sorted(user.education_entries.all(), key=lambda e: _edu_sort_val(e.years), reverse=True)
    # New: ensure achievements, experiences, and projects are ordered by most recent year
    def _latest_year(s):
        import re
        if not s:
            return -1
        s = s.replace('–', '-').replace('—', '-')
        years = re.findall(r'(?:19|20)\d{2}', s)
        return int(years[-1]) if years else -1
    achievements = sorted(user.achievements.all(), key=lambda a: _latest_year(a.year), reverse=True)
    work_qs = user.experiences.filter(category='work').prefetch_related('points')
    affiliation_qs = user.experiences.filter(category='affiliation').prefetch_related('points')
    work_experiences = sorted(work_qs, key=lambda e: _latest_year(e.years), reverse=True)
    affiliation_experiences = sorted(affiliation_qs, key=lambda e: _latest_year(e.years), reverse=True)
    projects_qs = user.projects.prefetch_related('points', 'images')
    projects = sorted(projects_qs, key=lambda p: _latest_year(p.year), reverse=True)
    # Selected Publications: exclude items flagged as ongoing research
    publications = (
        user.publications.filter(is_ongoing=False)
        .prefetch_related('authors', 'images')
        .order_by('-publication_year', '-id')
    )
    # Ongoing research projects (flagged within Publication)
    ongoing_projects = (
        user.publications.filter(is_ongoing=True)
        .prefetch_related('authors', 'images', 'contributions')
        .order_by('-publication_year', '-id')
    )

    pub_work_types = dict(Publication.WORK_TYPES)
    pub_research_areas = {r.key: r.name for r in ResearchArea.objects.order_by('display_order', 'id')}

    context = {
        'view_user': user,
        'profile': profile,
        'interests': interests,
        'education_entries': education_entries,
        'achievements': achievements,
        'work_experiences': work_experiences,
        'affiliation_experiences': affiliation_experiences,
        'projects': projects,
        'publications': publications,
        'ongoing_projects': ongoing_projects,
        'pub_work_types': pub_work_types,
        'pub_research_areas': pub_research_areas,
    }
    return render(request, 'lab/public_profile.html', context)


def cv_pdf(request, username):
    from django.shortcuts import get_object_or_404
    from .models import UserProfile
    user = get_object_or_404(User, username=username)
    if user.is_superuser:
        raise Http404("CV not available")
    profile = getattr(user, 'profile', None)
    if not profile or not profile.cv_pdf:
        raise Http404("CV not available")
    try:
        f = open(profile.cv_pdf.path, 'rb')
    except Exception:
        raise Http404("CV file missing")
    resp = FileResponse(f, content_type='application/pdf')
    resp['Content-Disposition'] = 'inline; filename="cv.pdf"'
    # Allow embedding to avoid Chrome “refused to connect” in iframe
    resp['X-Frame-Options'] = 'ALLOWALL'
    return resp


@login_required
def admin_content_actions(request):
    if not request.user.is_superuser:
        raise Http404
    if request.method != 'POST':
        return redirect('home')
    action = request.POST.get('action')
    next_url = request.POST.get('next') or '/'
    if action == 'set_order':
        model = request.POST.get('model')
        obj_id = request.POST.get('id')
        try:
            order = int(request.POST.get('order', '0'))
        except Exception:
            order = 0
        obj = None
        if model == 'profile':
            from .models import UserProfile
            obj = UserProfile.objects.filter(id=obj_id).first()
        elif model == 'publication':
            from .models import Publication
            obj = Publication.objects.filter(id=obj_id).first()
        if obj:
            obj.display_order = order
            obj.save(update_fields=['display_order'])
            messages.success(request, 'Order updated.')
        else:
            messages.error(request, 'Item not found.')
        return redirect(next_url)
    elif action == 'delete_publication':
        from .models import Publication
        pid = request.POST.get('publication_id')
        # Soft-delete for public tabs only: keep on user profiles
        updated = Publication.objects.filter(id=pid).update(show_on_public_pages=False)
        # Also hide clones (same title/year with overlapping authors) from aggregated tabs
        try:
            from .models import PublicationAuthor
            src = Publication.objects.filter(id=pid).first()
            if src:
                author_emails = [
                    (a.mail or '').strip().lower()
                    for a in PublicationAuthor.objects.filter(publication=src)
                    if getattr(a, 'mail', None)
                ]
                if author_emails:
                    clone_qs = (
                        Publication.objects
                        .filter(title__iexact=src.title, authors__mail__in=author_emails)
                        .exclude(id=src.id)
                        .distinct()
                    )
                    clone_qs.update(show_on_public_pages=False)
        except Exception:
            pass
        if updated:
            messages.success(request, 'Publication removed from Publications/Research tabs (still visible on profile).')
        else:
            messages.error(request, 'Publication not found.')
        return redirect(next_url)
    return redirect('home')


def change_password(request):
    if not request.user.is_authenticated:
        return redirect('login')
    user = request.user
    from django.contrib.auth import update_session_auth_hash
    profile = getattr(user, 'profile', None)
    if request.method == 'POST':
        current = request.POST.get('current_password', '')
        new1 = request.POST.get('new_password', '')
        new2 = request.POST.get('confirm_password', '')
        if not user.check_password(current):
            messages.error(request, 'Current password is incorrect.')
        elif len(new1) < 8:
            messages.error(request, 'New password must be at least 8 characters.')
        elif new1 != new2:
            messages.error(request, 'New passwords do not match.')
        else:
            user.set_password(new1)
            user.save()
            if profile:
                profile.must_change_password = False
                profile.save(update_fields=['must_change_password'])
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully.')
            return redirect('home')
    return render(request, 'lab/change_password.html')


# Admin: bulk reorder endpoint for profiles and publications
@login_required
def admin_reorder(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "not_authorized"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    import json
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    model = data.get("model")
    ids = data.get("ids")
    group = data.get("group")  # optional context: role, research area, user group

    if isinstance(ids, str):
        ids = [int(x) for x in ids.split(",") if x]
    elif isinstance(ids, list):
        ids = [int(x) for x in ids if str(x).isdigit()]

    if not ids:
        return JsonResponse({"error": "no_ids"}, status=400)

    if model == "profile":
        from .models import UserProfile
        qs = UserProfile.objects.filter(id__in=ids)
        if group:
            qs = qs.filter(role=group)
        order_map = {pid: i + 1 for i, pid in enumerate(ids)}
        for obj in qs:
            new_order = order_map.get(obj.id)
            if new_order is not None:
                obj.display_order = new_order
                obj.save(update_fields=["display_order"])
        return JsonResponse({"status": "ok"})

    elif model == "publication":
        from .models import Publication
        qs = Publication.objects.filter(id__in=ids)
        order_map = {pid: i + 1 for i, pid in enumerate(ids)}
        for obj in qs:
            new_order = order_map.get(obj.id)
            if new_order is not None:
                obj.display_order = new_order
                obj.save(update_fields=["display_order"])
        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "model_invalid"}, status=400)
