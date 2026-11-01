from django.conf import settings
from django.db import models

from .crypto import decrypt, encrypt


class Platform(models.TextChoices):
    META = "meta", "Meta Ads"
    GOOGLE = "google", "Google Ads"
    TIKTOK = "tiktok", "TikTok Ads"
    OPENAI = "openai", "ChatGPT Ads"


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending approval"
    SCHEDULED = "scheduled", "Scheduled"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"
    ERROR = "error", "Error"
    ARCHIVED = "archived", "Archived"


class PlatformConnection(models.Model):
    """An authorised link to an ad platform (one OAuth grant). Tokens are encrypted at rest."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Connected"
        EXPIRED = "expired", "Token expired"
        ERROR = "error", "Error"
        REVOKED = "revoked", "Disconnected"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE, related_name="connections")
    platform = models.CharField(max_length=20, choices=Platform.choices)
    label = models.CharField(max_length=120)
    external_user_id = models.CharField(max_length=120, blank=True)
    _access_token = models.TextField(db_column="access_token", blank=True)
    _refresh_token = models.TextField(db_column="refresh_token", blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    last_error = models.CharField(max_length=300, blank=True)
    connected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["platform", "label"]

    def __str__(self):
        return f"{self.get_platform_display()} · {self.label}"

    @property
    def access_token(self):
        return decrypt(self._access_token)

    @access_token.setter
    def access_token(self, value):
        self._access_token = encrypt(value)

    @property
    def refresh_token(self):
        return decrypt(self._refresh_token)

    @refresh_token.setter
    def refresh_token(self, value):
        self._refresh_token = encrypt(value)


class AdAccount(models.Model):
    class SyncStatus(models.TextChoices):
        NEVER = "never", "Not synced yet"
        OK = "ok", "Healthy"
        PARTIAL = "partial", "Partial sync"
        FAILED = "failed", "Sync failed"
        MANUAL = "manual", "Manual reporting"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE, related_name="ad_accounts")
    client = models.ForeignKey(
        "workspace.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="ad_accounts"
    )
    connection = models.ForeignKey(
        PlatformConnection, on_delete=models.SET_NULL, null=True, blank=True, related_name="ad_accounts"
    )
    platform = models.CharField(max_length=20, choices=Platform.choices)
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=150)
    currency = models.CharField(max_length=3, default="INR")
    timezone = models.CharField(max_length=40, default="Asia/Kolkata")
    is_manual = models.BooleanField(default=False, help_text="Results are entered by hand, not synced by API.")
    sync_status = models.CharField(max_length=10, choices=SyncStatus.choices, default=SyncStatus.NEVER)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["platform", "name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "platform", "external_id"], name="unique_ad_account")
        ]

    def __str__(self):
        return self.name


class Campaign(models.Model):
    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE, related_name="campaigns")
    client = models.ForeignKey(
        "workspace.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="campaigns"
    )
    ad_account = models.ForeignKey(AdAccount, on_delete=models.CASCADE, related_name="campaigns")
    platform = models.CharField(max_length=20, choices=Platform.choices)
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    objective = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    daily_budget_paise = models.BigIntegerField(null=True, blank=True)
    lifetime_budget_paise = models.BigIntegerField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["ad_account", "external_id"], name="unique_campaign_per_account")
        ]

    def __str__(self):
        return self.name


class AdSet(models.Model):
    """Meta ad set / Google, TikTok and ChatGPT ad group."""

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.SET_NULL, null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="ad_sets")
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    daily_budget_paise = models.BigIntegerField(null=True, blank=True)
    targeting = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ad(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "In review"
        APPROVED = "approved", "Approved"
        DISAPPROVED = "disapproved", "Disapproved"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.SET_NULL, null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="ads")
    ad_set = models.ForeignKey(AdSet, on_delete=models.CASCADE, related_name="ads")
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    review_status = models.CharField(max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    creative = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MetricSnapshot(models.Model):
    """One day of a campaign's results, as reported by the platform (or entered by hand)."""

    class Source(models.TextChoices):
        API = "api", "Platform API"
        MANUAL = "manual", "Manual entry"
        SANDBOX = "sandbox", "Sandbox data"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.SET_NULL, null=True, blank=True)
    ad_account = models.ForeignKey(AdAccount, on_delete=models.CASCADE, related_name="metrics")
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="metrics")
    platform = models.CharField(max_length=20, choices=Platform.choices)
    date = models.DateField()
    spend_paise = models.BigIntegerField(default=0)
    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(null=True, blank=True)
    leads = models.BigIntegerField(default=0)
    conversions = models.BigIntegerField(default=0)
    # Null when revenue tracking is not connected; ROAS is only shown where this is known.
    revenue_paise = models.BigIntegerField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.API)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["campaign", "date"], name="unique_campaign_day")]
        indexes = [models.Index(fields=["organization", "date"])]

    def __str__(self):
        return f"{self.campaign} {self.date}"
