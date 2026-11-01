from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "actor", "action", "entity_type", "entity_label", "outcome"]
    list_filter = ["outcome", "action"]
    readonly_fields = [f.name for f in AuditEvent._meta.fields]
