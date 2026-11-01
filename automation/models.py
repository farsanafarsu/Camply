from django.conf import settings
from django.db import models


class Rule(models.Model):
    """A check Camply runs on a schedule. Rules alert people; they never change campaigns by themselves."""

    class Kind(models.TextChoices):
        CLIENT_BUDGET = "client_budget", "Client monthly budget reaches a percentage"
        CAMPAIGN_DAILY = "campaign_daily", "Campaign spent most of its daily budget yesterday"
        CPL_ABOVE = "cpl_above", "Cost per lead above a limit"
        NO_DELIVERY = "no_delivery", "Active campaign with no impressions"
        SYNC_FAILURE = "sync_failure", "Ad account sync failed"
        APPROVAL_REMINDER = "approval_reminder", "Creatives or changes waiting for approval"
        GUARDED_PAUSE = "guarded_pause", "Suggest pausing campaigns with high cost per lead"
        SCHEDULED_REPORT = "scheduled_report", "Email a performance summary"

    # Which settings each kind uses, shown on the form.
    PARAMS = {
        Kind.CLIENT_BUDGET: ["percent"],
        Kind.CAMPAIGN_DAILY: ["percent"],
        Kind.CPL_ABOVE: ["cpl_rupees", "days"],
        Kind.NO_DELIVERY: ["days"],
        Kind.SYNC_FAILURE: [],
        Kind.APPROVAL_REMINDER: ["days"],
        Kind.GUARDED_PAUSE: ["cpl_rupees", "days"],
        Kind.SCHEDULED_REPORT: ["frequency"],
    }

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE, related_name="rules")
    client = models.ForeignKey("workspace.Client", on_delete=models.CASCADE, null=True, blank=True,
                               help_text="Leave empty to check every client")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    params = models.JSONField(default=dict, blank=True)
    notify_email = models.BooleanField(default=True)
    recipients = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def summary(self):
        p = self.params
        bits = {
            self.Kind.CLIENT_BUDGET: f"at {p.get('percent', 80)}% of the monthly budget",
            self.Kind.CAMPAIGN_DAILY: f"at {p.get('percent', 100)}% of the daily budget",
            self.Kind.CPL_ABOVE: f"cost per lead over ₹{p.get('cpl_rupees', '?')} (last {p.get('days', 7)} days)",
            self.Kind.NO_DELIVERY: f"no impressions for {p.get('days', 2)} days",
            self.Kind.SYNC_FAILURE: "when a sync fails",
            self.Kind.APPROVAL_REMINDER: f"waiting more than {p.get('days', 2)} days",
            self.Kind.GUARDED_PAUSE: f"cost per lead over ₹{p.get('cpl_rupees', '?')} (last {p.get('days', 7)} days); asks for approval",
            self.Kind.SCHEDULED_REPORT: f"{p.get('frequency', 'weekly')} summary email",
        }
        return bits.get(self.kind, "")


class Alert(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE, related_name="alerts")
    client = models.ForeignKey("workspace.Client", on_delete=models.CASCADE, null=True, blank=True)
    rule = models.ForeignKey(Rule, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=30)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    # Same key while the problem lasts, so a rule doesn't raise the same alert every hour.
    dedupe_key = models.CharField(max_length=200)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "resolved_at"])]

    def __str__(self):
        return self.title


class ActionRequest(models.Model):
    """A change to spend or status that waits for a person to approve it before Camply applies it."""

    class Action(models.TextChoices):
        PAUSE = "pause", "Pause campaign"
        RESUME = "resume", "Resume campaign"
        SET_DAILY_BUDGET = "set_daily_budget", "Change daily budget"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPLIED = "applied", "Approved and applied"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Approved, but the platform refused"

    class Source(models.TextChoices):
        USER = "user", "Team member"
        RULE = "rule", "Automation rule"
        COPILOT = "copilot", "AI Copilot"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.SET_NULL, null=True, blank=True)
    campaign = models.ForeignKey("ads.Campaign", on_delete=models.CASCADE, related_name="action_requests")
    action = models.CharField(max_length=20, choices=Action.choices)
    payload = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.USER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    result_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()}: {self.campaign}"

    @property
    def description(self):
        if self.action == self.Action.SET_DAILY_BUDGET:
            from camply.money import format_inr

            return (f"Change daily budget from {format_inr(self.payload.get('from_paise'))} "
                    f"to {format_inr(self.payload.get('to_paise'))}")
        return self.get_action_display()
