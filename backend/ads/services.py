"""Sync and campaign actions. Views and Celery tasks call these; they never call adapters directly."""

import logging
from datetime import timedelta

from django.utils import timezone

from audit import log as audit

from .adapters import AdapterError, AuthExpired, Capability, NotConfigured, adapter_for_account
from .adapters.sandbox import SandboxAdapter
from .models import AdAccount, Campaign, CampaignStatus, MetricSnapshot, PlatformConnection

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30


def _results_changed(organization_id):
    """Drop cached dashboard/report numbers for this agency."""
    from dashboard.analytics import invalidate

    invalidate(organization_id)


def today_ist():
    return timezone.localdate()


def sync_account(account: AdAccount, *, days: int = DEFAULT_LOOKBACK_DAYS, actor=None, request=None) -> dict:
    """Pull campaigns and daily metrics for one ad account and upsert them.

    Returns a summary dict. Failures are recorded on the account (and its connection,
    for auth errors) and in the audit log, then re-raised as AdapterError.
    """
    if account.is_manual:
        return {"campaigns": 0, "rows": 0, "skipped": "manual"}

    end = today_ist()
    start = end - timedelta(days=days - 1)
    try:
        adapter = adapter_for_account(account)
        remote_campaigns = adapter.list_campaigns(account)
        rows = adapter.fetch_daily_metrics(account, start, end)
    except AdapterError as exc:
        account.sync_status = AdAccount.SyncStatus.FAILED
        account.last_sync_error = str(exc)[:300]
        account.save(update_fields=["sync_status", "last_sync_error"])
        if isinstance(exc, AuthExpired) and account.connection_id:
            PlatformConnection.objects.filter(pk=account.connection_id).update(
                status=PlatformConnection.Status.EXPIRED, last_error=str(exc)[:300]
            )
        audit.record(
            organization=account.organization, action="sync", entity=account, actor=actor, request=request,
            outcome="failed", message=str(exc),
        )
        raise

    source = MetricSnapshot.Source.SANDBOX if isinstance(adapter, SandboxAdapter) else MetricSnapshot.Source.API
    by_external_id = {}
    for remote in remote_campaigns:
        campaign, _ = Campaign.objects.update_or_create(
            ad_account=account,
            external_id=remote.external_id,
            defaults={
                "organization_id": account.organization_id,
                "client_id": account.client_id,
                "platform": account.platform,
                "name": remote.name,
                "objective": remote.objective,
                "status": remote.status,
                "daily_budget_paise": remote.daily_budget_paise,
                "lifetime_budget_paise": remote.lifetime_budget_paise,
                "start_date": remote.start_date,
                "end_date": remote.end_date,
            },
        )
        by_external_id[remote.external_id] = campaign

    written = 0
    unmatched = 0
    for row in rows:
        campaign = by_external_id.get(row.campaign_external_id)
        if campaign is None:
            unmatched += 1
            continue
        MetricSnapshot.objects.update_or_create(
            campaign=campaign,
            date=row.date,
            defaults={
                "organization_id": account.organization_id,
                "client_id": account.client_id,
                "ad_account": account,
                "platform": account.platform,
                "spend_paise": row.spend_paise,
                "impressions": row.impressions,
                "clicks": row.clicks,
                "reach": row.reach,
                "leads": row.leads,
                "conversions": row.conversions,
                "revenue_paise": row.revenue_paise,
                "source": source,
            },
        )
        written += 1

    account.sync_status = AdAccount.SyncStatus.PARTIAL if unmatched else AdAccount.SyncStatus.OK
    account.last_sync_error = f"{unmatched} rows referenced unknown campaigns." if unmatched else ""
    account.last_synced_at = timezone.now()
    account.save(update_fields=["sync_status", "last_sync_error", "last_synced_at"])
    summary = {"campaigns": len(by_external_id), "rows": written, "unmatched": unmatched}
    _results_changed(account.organization_id)
    audit.record(
        organization=account.organization, action="sync", entity=account, actor=actor, request=request,
        after=summary,
    )
    return summary


def set_campaign_status(campaign: Campaign, new_status: str, *, actor, request=None):
    """Pause or resume a campaign on its platform, then record it locally and in the audit log."""
    if new_status not in (CampaignStatus.ACTIVE, CampaignStatus.PAUSED):
        raise ValueError("Only pause and resume are supported.")
    adapter = adapter_for_account(campaign.ad_account)
    before = {"status": campaign.status}
    try:
        if new_status == CampaignStatus.PAUSED:
            adapter.require(Capability.PAUSE)
            adapter.pause_campaign(campaign)
        else:
            adapter.require(Capability.RESUME)
            adapter.resume_campaign(campaign)
    except (AdapterError, NotConfigured) as exc:
        audit.record(
            organization=campaign.organization, action="campaign.status", entity=campaign, actor=actor,
            request=request, before=before, after={"status": new_status}, outcome="failed", message=str(exc),
        )
        raise
    campaign.status = new_status
    campaign.save(update_fields=["status", "updated_at"])
    _results_changed(campaign.organization_id)
    audit.record(
        organization=campaign.organization, action="campaign.status", entity=campaign, actor=actor,
        request=request, before=before, after={"status": new_status},
    )


def set_daily_budget(campaign: Campaign, daily_budget_paise: int, *, actor, request=None):
    """Change a campaign's daily budget on its platform, then locally, with an audit record."""
    if daily_budget_paise <= 0:
        raise ValueError("The daily budget must be more than zero.")
    adapter = adapter_for_account(campaign.ad_account)
    before = {"daily_budget_paise": campaign.daily_budget_paise}
    after = {"daily_budget_paise": daily_budget_paise}
    try:
        adapter.require(Capability.UPDATE_BUDGET)
        adapter.update_daily_budget(campaign, daily_budget_paise)
    except AdapterError as exc:
        audit.record(organization=campaign.organization, action="campaign.budget", entity=campaign, actor=actor,
                     request=request, before=before, after=after, outcome="failed", message=str(exc))
        raise
    campaign.daily_budget_paise = daily_budget_paise
    campaign.save(update_fields=["daily_budget_paise", "updated_at"])
    _results_changed(campaign.organization_id)
    audit.record(organization=campaign.organization, action="campaign.budget", entity=campaign, actor=actor,
                 request=request, before=before, after=after)
