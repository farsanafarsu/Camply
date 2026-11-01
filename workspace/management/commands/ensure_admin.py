"""Create or update the first admin account from environment variables.

Safe to run on every deploy (e.g. in Render's start command):

    python manage.py migrate && python manage.py ensure_admin && gunicorn camply.wsgi

Reads:
    CAMPLY_ADMIN_EMAIL      the admin's email (required; does nothing if unset)
    CAMPLY_ADMIN_PASSWORD   their password (required with the email)
    CAMPLY_ORG_NAME         organization to make them Owner of (default "PRception Media")

The account is made a verified Owner of that organization with Django admin access.
The password is reset to CAMPLY_ADMIN_PASSWORD each time, so changing the variable and
redeploying changes the password.
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
        if not password:
            raise CommandError("CAMPLY_ADMIN_PASSWORD must be set together with CAMPLY_ADMIN_EMAIL.")

        from allauth.account.models import EmailAddress

        org_name = (os.environ.get("CAMPLY_ORG_NAME") or "PRception Media").strip()
        org = Organization.objects.filter(name__iexact=org_name).first()
        if org is None:
            org = Organization.objects.create(name=org_name, state="Kerala", city="Thiruvananthapuram")

        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        if created:
            user = User(email=email)
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

        Membership.objects.update_or_create(
            organization=org, user=user, defaults={"role": Role.OWNER, "all_clients": True}
        )
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"Camply admin setup: {action} admin {email} as Owner of {org.name} "
            f"(password length {len(password)})."
        ))
