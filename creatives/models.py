from django.conf import settings
from django.db import models

from ads.models import Platform


class Creative(models.Model):
    """An image, video, piece of ad copy or landing page, with its approval status."""

    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        COPY = "copy", "Ad copy"
        LANDING = "landing", "Landing page"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        INTERNAL_REVIEW = "internal_review", "Internal review"
        CLIENT_APPROVAL = "client_approval", "Client approval"
        READY = "ready", "Ready to publish"
        REJECTED = "rejected", "Rejected"

    class CTA(models.TextChoices):
        NONE = "", "None"
        LEARN_MORE = "learn_more", "Learn more"
        SIGN_UP = "sign_up", "Sign up"
        BOOK_NOW = "book_now", "Book now"
        SHOP_NOW = "shop_now", "Shop now"
        CONTACT_US = "contact_us", "Contact us"
        GET_QUOTE = "get_quote", "Get quote"
        APPLY_NOW = "apply_now", "Apply now"
        CALL_NOW = "call_now", "Call now"
        WHATSAPP = "whatsapp", "Send WhatsApp message"

    LANGUAGES = [("en", "English"), ("ml", "Malayalam"), ("hi", "Hindi"), ("ta", "Tamil"), ("other", "Other")]

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.CASCADE, related_name="creatives")
    campaign = models.ForeignKey("ads.Campaign", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="creatives", help_text="Campaign this creative is for, if any")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.IMAGE)
    file = models.FileField(upload_to="creatives/%Y/%m/", blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    landing_url = models.URLField(blank=True)
    headline = models.CharField(max_length=255, blank=True)
    primary_text = models.TextField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    cta = models.CharField("Call to action", max_length=20, choices=CTA.choices, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=10, choices=LANGUAGES, default="en")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    root = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="versions",
                             help_text="The first version; empty on the first version itself")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} (v{self.version})" if self.version > 1 else self.name

    @property
    def is_image(self):
        return self.kind == self.Kind.IMAGE and bool(self.file)

    @property
    def platform_labels(self):
        return [Platform(p).label for p in self.platforms if p in Platform.values]


class CreativeReview(models.Model):
    """One step in a creative's approval history."""

    class Action(models.TextChoices):
        SUBMITTED = "submit", "Submitted for review"
        APPROVED_INTERNAL = "approve_internal", "Approved internally, sent to client"
        APPROVED_CLIENT = "approve_client", "Approved by client"
        CHANGES = "request_changes", "Changes requested"
        REJECTED = "reject", "Rejected"

    creative = models.ForeignKey(Creative, on_delete=models.CASCADE, related_name="reviews")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
