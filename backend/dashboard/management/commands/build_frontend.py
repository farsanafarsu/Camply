"""Build the public website as plain static files for Cloudflare (frontend/dist/).

    python backend/manage.py build_frontend --app-url https://app.camply.in

Renders the marketing home page to index.html, copies frontend/static/ beside it, and
points every sign-in / sign-up link at the Django app (which stays on the backend host).
Run it locally (DEBUG on) so static paths are plain, unhashed /static/... URLs.
"""

import os
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from dashboard.views import home

DEFAULT_APP_URL = "https://camply-tcee.onrender.com"


class Command(BaseCommand):
    help = "Render the public home page and static files into frontend/dist/ for Cloudflare."

    def add_arguments(self, parser):
        parser.add_argument("--app-url", default=os.environ.get("CAMPLY_APP_URL", DEFAULT_APP_URL),
                            help="Where the Django app is hosted (sign-in links go there).")
        parser.add_argument("--out", default=str(settings.FRONTEND_DIR / "dist"))

    def handle(self, *args, app_url, out, **options):
        app_url = app_url.rstrip("/")
        if not app_url.startswith("https://"):
            raise CommandError("--app-url must start with https://")
        if "Manifest" in settings.STORAGES["staticfiles"]["BACKEND"]:
            raise CommandError("Run with DJANGO_DEBUG=true so static URLs are plain (no manifest hashes).")

        out_dir = Path(out)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        # 1. Static files: CSS, JS, images, vendored libraries.
        shutil.copytree(settings.FRONTEND_DIR / "static", out_dir / "static")

        # 2. The home page, rendered as an anonymous visitor sees it.
        request = RequestFactory().get("/", HTTP_HOST="localhost")
        request.user = AnonymousUser()
        request.membership = None
        request.organization = None
        html = home(request).content.decode("utf-8")
        html = self._link_to_app(html, app_url)
        (out_dir / "index.html").write_text(html, encoding="utf-8")

        # 3. A simple not-found page and cache headers for Cloudflare.
        (out_dir / "404.html").write_text(NOT_FOUND.replace("{APP}", app_url), encoding="utf-8")
        (out_dir / "_headers").write_text(HEADERS, encoding="utf-8")

        files = sum(1 for p in out_dir.rglob("*") if p.is_file())
        self.stdout.write(self.style.SUCCESS(f"Built {files} files into {out_dir} (app links -> {app_url})."))

    @staticmethod
    def _link_to_app(html, app_url):
        """Send account links (/accounts/...) to the Django app; keep in-page anchors and static paths."""
        return re.sub(r'(href|action)="(/accounts/[^"]*)"', lambda m: f'{m.group(1)}="{app_url}{m.group(2)}"', html)


NOT_FOUND = """<!doctype html>
<html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page not found · Camply</title><link rel="stylesheet" href="/static/css/camply.css"></head>
<body><div class="auth-simple empty"><h1>Page not found</h1>
<p>That page doesn't exist. Looking for your dashboard?</p>
<p><a class="btn btn-primary" href="{APP}/accounts/login/">Sign in to Camply</a> <a class="btn" href="/">Home</a></p></div></body></html>
"""

# Static file names aren't fingerprinted, so cache for an hour and let browsers revalidate.
HEADERS = """/static/*
  Cache-Control: public, max-age=3600, must-revalidate
/
  Cache-Control: public, max-age=300
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
"""
