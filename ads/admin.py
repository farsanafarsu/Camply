from django.contrib import admin

from .models import Ad, AdAccount, AdSet, Campaign, MetricSnapshot, PlatformConnection


@admin.register(PlatformConnection)
class PlatformConnectionAdmin(admin.ModelAdmin):
    list_display = ["label", "platform", "organization", "status", "created_at"]
    exclude = ["_access_token", "_refresh_token"]


@admin.register(AdAccount)
class AdAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "platform", "organization", "client", "sync_status", "last_synced_at"]
    list_filter = ["platform", "sync_status"]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["name", "platform", "client", "status", "daily_budget_paise"]
    list_filter = ["platform", "status"]
    search_fields = ["name"]


admin.site.register(AdSet)
admin.site.register(Ad)


@admin.register(MetricSnapshot)
class MetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ["campaign", "date", "spend_paise", "impressions", "clicks", "leads", "source"]
    list_filter = ["platform", "source"]
