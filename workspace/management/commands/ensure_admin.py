"""Create or update the first admin account from environment variables.

Safe to run on every deploy (e.g. in Render's start command):

    python manage.py migrate && python manage.py ensure_admin && gunicorn camply.wsgi

Reads:
    CAMPLY_ADMIN_EMAIL      the admin's email (required; does nothing if unset)
    CAMPLY_ADMIN_PASSWORD   their password (required with the email)
    CAMPLY_ORG_NAME         optional: also make them Owner of this organization (created if needed)
    CAMPLY_ADMIN_RESET_PASSWORD  "true" to overwrite an existing account's password

The account is a verified platform admin (superuser) who signs in to the platform console.
The password is set when the account is created. After that it is left alone (so a
password changed in the app, or through "Forgot password", survives restarts) unless
CAMPLY_ADMIN_RESET_PASSWORD is true.
"""

import os

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from workspace.models import Membership, Organization, Role


class Command(BaseCommand):
    help = "Create or update the admin account from CAMPLY_ADMIN_EMAIL and CAMPLY_ADMIN_PASSWORD."

    def handle(self, *args, **options):
        email = (os.environ.get("CAMPLY_ADMIN_EMAIL") or "").strip().lower()
        # Spaces pasted around the value in a hosting dashboard are a common cause of failed sign-ins.
        password = (os.environ.get("CAMPLY_ADMIN_PASSWORD") or "").strip()
        if not email:
            self.stdout.write("Camply admin setup: CAMPLY_ADMIN_EMAIL is not set; skipping.")
            return

        from allauth.account.models import EmailAddress

        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        if created and not password:
            raise CommandError("Set CAMPLY_ADMIN_PASSWORD to create the admin account for CAMPLY_ADMIN_EMAIL.")
        reset = bool(password) and (
            (os.environ.get("CAMPLY_ADMIN_RESET_PASSWORD") or "").strip().lower() in {"1", "true", "yes"}
        )
        if created:
            user = User(email=email)
        if created or reset:
            user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save()

        EmailAddress.objects.filter(user=user).exclude(email__iexact=email).update(primary=False)
        address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
        if address is None:
            EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        else:
            address.verified = True
            address.primary = True
            address.save(update_fields=["verified", "primary"])

        org_note = ""
        org_name = (os.environ.get("CAMPLY_ORG_NAME") or "").strip()
        if org_name:
            org = Organization.objects.filter(name__iexact=org_name).first()
            if org is None:
                org = Organization.objects.create(name=org_name, state="Kerala", city="Thiruvananthapuram")
            Membership.objects.update_or_create(
                organization=org, user=user, defaults={"role": Role.OWNER, "all_clients": True}
            )
            org_note = f" and Owner of {org.name}"

        if created:
            outcome = f"Created platform admin {email}{org_note} (password length {len(password)})."
        elif reset:
            outcome = f"Updated admin {email}; password reset from CAMPLY_ADMIN_PASSWORD (length {len(password)})."
        elif password:
            # Says whether signing in with the Render value would work, without revealing anything.
            matches = "yes" if user.check_password(password) else "no"
            outcome = (f"Admin {email} already exists; password left unchanged. "
                       f"Does CAMPLY_ADMIN_PASSWORD match the account's password? {matches}.")
        else:
            outcome = f"Admin {email} already exists; password left unchanged."
        self.stdout.write(self.style.SUCCESS(f"Camply admin setup: {outcome}"))
