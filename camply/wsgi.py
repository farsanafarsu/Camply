import logging
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "camply.settings")

application = get_wsgi_application()


def _ensure_admin():
    """Create/update the admin from CAMPLY_ADMIN_EMAIL / CAMPLY_ADMIN_PASSWORD when the server starts.

    Runs in every web worker so a deploy works even if the start command doesn't call
    `manage.py ensure_admin`. It's idempotent; a failure is logged and never stops the site.
    """
    from django.core.management import call_command

    try:
        call_command("ensure_admin")
    except Exception:
        logging.getLogger("camply").exception("Camply admin setup failed at startup")


_ensure_admin()
