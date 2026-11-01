import secrets

from django.conf import settings
from django.db import models


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        MEETING = "meeting", "Meeting booked"
        WON = "won", "Won"
        LOST = "lost", "Lost"
        INVALID = "invalid", "Invalid"

    class Source(models.TextChoices):
        MANUAL = "manual", "Added by hand"
        WEBHOOK = "webhook", "Website form"
        PLATFORM = "platform", "Ad platform lead form"
        IMPORT = "import", "Imported"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.CASCADE, related_name="leads")
    campaign = models.ForeignKey("ads.Campaign", on_delete=models.SET_NULL, null=True, blank=True)
    platform = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=80, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="assigned_leads")
    value_paise = models.BigIntegerField(null=True, blank=True, help_text="Deal value when won")
    consent = models.BooleanField(default=False, help_text="The person agreed to be contacted")
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=150, blank=True)
    utm_content = models.CharField(max_length=150, blank=True)
    utm_term = models.CharField(max_length=150, blank=True)
    duplicate_of = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)
    remind_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return self.full_name or self.email or self.phone or "Lead"


class LeadNote(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


def _token():
    return secrets.token_urlsafe(24)


class LeadWebhook(models.Model):
    """A secret URL a client's website form posts leads to."""

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.OneToOneField("workspace.Client", on_delete=models.CASCADE, related_name="lead_webhook")
    token = models.CharField(max_length=64, unique=True, default=_token)
    created_at = models.DateTimeField(auto_now_add=True)


def find_duplicate(lead):
    """An earlier lead for the same client with the same email or phone, if any."""
    from django.db.models import Q

    match = Q()
    if lead.email:
        match |= Q(email__iexact=lead.email)
    if lead.phone:
        match |= Q(phone=normalise_phone(lead.phone))
    if not match:
        return None
    qs = Lead.objects.filter(match, client_id=lead.client_id, duplicate_of__isnull=True)
    if lead.pk:
        qs = qs.exclude(pk=lead.pk)
    return qs.order_by("created_at").first()


def normalise_phone(phone):
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits
