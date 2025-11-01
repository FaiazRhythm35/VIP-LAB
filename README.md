# VIP Lab Host Website — Directory & Overview

This repository contains a Django-based website for a research lab. It manages public pages (home, research areas, publications, people, about) and user-facing features (login, password reset/change, profile pages), along with admin/user management utilities.

## Directory Structure (simplified)

```
VIP Lab host/
├── manage.py                 # Django management entrypoint
├── db.sqlite3                # Local SQLite database (development)
├── vip_site/                 # Project config (settings, root URLs, WSGI/ASGI)
├── lab/                      # Main app (models, views, URLs, admin, middleware)
├── templates/                # HTML templates (base layout + lab pages)
├── static/                   # CSS, JS, and static images used by templates
├── media/                    # Uploaded/media assets (profiles, awards, publications)
└── venv/                     # Python virtual environment
```

## What The Website Does

- Shows a public homepage, about page, and research areas with detail pages.
- Lists publications with associated images and optional metadata (e.g., research area tags).
- Displays lab people and individual public profile pages.
- Presents awards and news items (seeded via migrations) on public pages.
- Provides user authentication: login, password reset, and change password flows.
- Includes an admin-facing user management page.
- Offers a site-wide search page.
- Uses custom template tags for profile links and text formatting.

## Key Folders & Files

- `manage.py` — CLI tool to run the server, apply migrations, and manage the project.
- `db.sqlite3` — Development database; data is created/modified via migrations and admin.

### Project: `vip_site/`
- `settings.py` — Django configuration (installed apps, database, static/media, etc.).
- `urls.py` — Root URL routing; includes the `lab` app routes.
- `wsgi.py` / `asgi.py` — Entry points for production servers and async servers.

### App: `lab/`
- `models.py` — Core data models such as user profiles, publications, research areas, awards/news, and about content.
- `views.py` — View functions that render pages like home, people, publications, research, profile, search, and auth-related pages.
- `urls.py` — App-level URL patterns mapped to views.
- `admin.py` — Django admin registrations for managing content.
- `middleware.py` — Custom middleware used by the app.
- `templatetags/`
  - `profile_links.py` — Utilities for generating consistent profile-related links.
  - `textformat.py` — Helpers for formatting text in templates.
- `migrations/` — Database migrations including seeds (e.g., default super admin, research areas, about content, awards/news).

### Templates: `templates/`
- `base.html` — Shared site layout, navigation, and static asset includes.
- `templates/lab/`
  - `home.html` — Public homepage.
  - `about.html` — About the lab.
  - `research.html` — Research areas list.
  - `research_detail.html` — Detail page for a specific research area.
  - `publications.html` — Publications listing.
  - `people.html` — People directory.
  - `profile.html` — User profile page (authenticated).
  - `public_profile.html` — Public-facing profile page.
  - `admin_users.html` — Admin-oriented user management UI.
  - `search.html` — Site-wide search results.
  - `login.html`, `forgot_password.html`, `reset_password.html`, `change_password.html` — Authentication pages.

### Static Assets: `static/`
- `css/` — Stylesheets (`home.css`, `pub_page.css`, `public_profile.css`, `styles.css`).
- `js/` — JavaScript (`script.js`) for interactive behavior.
- `image/` — Static images referenced by templates (lab/research images, logos).

### Media Files: `media/`
- `profiles/` — User profile pictures.
- `awards/` — Award and recognition images.
- `publications/` — Figures and images used in publication entries.
- `research_areas/` — Images representing each research area.
- `cv/` — Stored CVs or related documents.

### Environment: `venv/`
- Python virtual environment containing the project’s dependencies and executables.

## Page Map (by template)

- `home.html` — Landing page highlighting research and recent updates.
- `about.html` — Lab mission, background, and overview.
- `research.html` / `research_detail.html` — Explore research topics and details.
- `publications.html` — Browse publications with images and metadata.
- `people.html` / `profile.html` / `public_profile.html` — People listing, private profile, and public profile views.
- `admin_users.html` — Admin page for managing users.
- `search.html` — Search interface across site content.
- `login.html`, `forgot_password.html`, `reset_password.html`, `change_password.html` — User authentication flow.

---

This overview is intended to help new contributors quickly understand how the website is organized and what functionality it provides.
