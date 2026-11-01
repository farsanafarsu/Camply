from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Who did what, to which record, when — and what changed."""

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        DENIED = "denied", "Denied"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE, related_name="audit_events")
    client = models.ForeignKey("workspace.Client", on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=64, blank=True)
    entity_label = models.CharField(max_length=200, blank=True)
    platform = models.CharField(max_length=20, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.SUCCESS)
    message = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def __str__(self):
        return f"{self.action} {self.entity_type} {self.entity_label}"
