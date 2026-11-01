import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

INDIAN_STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]
STATE_CHOICES = [(s, s) for s in INDIAN_STATES]


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    CAMPAIGN_MANAGER = "campaign_manager", "Campaign manager"
    ANALYST = "analyst", "Analyst"
    FINANCE = "finance", "Finance"
    CLIENT = "client", "Client"
    VIEWER = "viewer", "Viewer"


class Organization(models.Model):
    """The tenant: an agency or business using Camply."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    legal_name = models.CharField(max_length=200, blank=True)
    gstin = models.CharField("GSTIN", max_length=15, blank=True)
    state = models.CharField(max_length=60, choices=STATE_CHOICES, default="Kerala")
    city = models.CharField(max_length=80, blank=True)
    billing_email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=40, default="Asia/Kolkata")
    currency = models.CharField(max_length=3, default="INR")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Organization, self.name)
        super().save(*args, **kwargs)

    @property
    def initial(self):
        return self.name[:1].upper()


class Client(models.Model):
    """A customer or brand the organization runs ads for (a client workspace)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160)
    industry = models.CharField(max_length=80, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    gstin = models.CharField("GSTIN", max_length=15, blank=True)
    state = models.CharField(max_length=60, choices=STATE_CHOICES, blank=True)
    monthly_budget_paise = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "slug"], name="unique_client_slug_per_org")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Client, self.name, organization=self.organization)
        super().save(*args, **kwargs)


class Membership(models.Model):
    """A user's role in an organization, and which clients they can see."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.VIEWER)
    all_clients = models.BooleanField(
        default=False, help_text="Access every client in the organization. Owners always have this."
    )
    clients = models.ManyToManyField(Client, blank=True, related_name="memberships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name"]
        constraints = [models.UniqueConstraint(fields=["organization", "user"], name="unique_membership")]

    def __str__(self):
        return f"{self.user} · {self.organization} ({self.get_role_display()})"

    @property
    def sees_all_clients(self):
        return self.role == Role.OWNER or self.all_clients


def _invite_token():
    return secrets.token_urlsafe(32)


def _invite_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.VIEWER)
    all_clients = models.BooleanField(default=False)
    clients = models.ManyToManyField(Client, blank=True)
    token = models.CharField(max_length=64, unique=True, default=_invite_token)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite {self.email} → {self.organization}"

    @property
    def is_pending(self):
        return self.accepted_at is None and self.expires_at > timezone.now()


def unique_slug(model, name, **scope):
    base = slugify(name)[:150] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug, **scope).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug
