from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.contrib import messages

class ForcePasswordChangeMiddleware:
    """
    If a logged-in user has `profile.must_change_password` set, redirect them
    to the change-password page, blocking navigation to other pages.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        path = request.path or '/'
        # Allow static and media
        static_url = getattr(settings, 'STATIC_URL', '/static/') or '/static/'
        media_url = getattr(settings, 'MEDIA_URL', '/media/') or '/media/'
        if path.startswith(static_url) or path.startswith(media_url):
            return self.get_response(request)

        if user and user.is_authenticated:
            profile = getattr(user, 'profile', None)
            if getattr(profile, 'must_change_password', False):
                allow_paths = {
                    reverse('change_password'),
                    reverse('logout'),
                    reverse('login'),
                    reverse('forgot_password'),
                    reverse('admin_users'),
                }
                # Allow admin login page for staff
                try:
                    allow_paths.add('/admin/')
                except Exception:
                    pass
                if path not in allow_paths:
                    try:
                        messages.warning(request, 'Please change your password to continue.')
                    except Exception:
                        pass
                    return redirect(f"{reverse('change_password')}?force_pw_change=1")
        return self.get_response(request)