"""Evaluate automation rules: raise alerts, propose guarded changes, send scheduled summaries."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Sum
from django.utils import timezone

from ads.models import AdAccount, Campaign, CampaignStatus, MetricSnapshot
from camply.money import format_inr
from creatives.models import Creative
from workspace.models import Client

from .models import ActionRequest, Alert, Rule

logger = logging.getLogger(__name__)


def _clients(rule):
    qs = Client.objects.filter(organization_id=rule.organization_id, is_active=True)
    return qs.filter(pk=rule.client_id) if rule.client_id else qs


def _campaigns(rule):
    qs = Campaign.objects.filter(organization_id=rule.organization_id).select_related("client")
    return qs.filter(client_id=rule.client_id) if rule.client_id else qs


def _metrics(rule, since):
    qs = MetricSnapshot.objects.filter(organization_id=rule.organization_id, date__gte=since)
    return qs.filter(client_id=rule.client_id) if rule.client_id else qs


def raise_alert(rule, *, key, title, body="", client=None, link="", severity=Alert.Severity.WARNING):
    """Create an alert unless the same problem already has an open one. Returns the new alert or None."""
    if Alert.objects.filter(organization_id=rule.organization_id, dedupe_key=key, resolved_at__isnull=True).exists():
        return None
    return Alert.objects.create(organization_id=rule.organization_id, client=client, rule=rule, kind=rule.kind,
                                severity=severity, title=title[:200], body=body, link=link, dedupe_key=key[:200])


def _client_budget(rule, today):
    percent = float(rule.params.get("percent", 80))
    month_start = today.replace(day=1)
    spend = {r["client_id"]: r["s"] for r in _metrics(rule, month_start).values("client_id").annotate(s=Sum("spend_paise"))}
    alerts = []
    for client in _clients(rule).exclude(monthly_budget_paise__isnull=True):
        used = (spend.get(client.pk) or 0) * 100 / client.monthly_budget_paise if client.monthly_budget_paise else 0
        if used >= percent:
            alerts.append(raise_alert(
                rule, key=f"client_budget:{client.pk}:{month_start:%Y-%m}:{int(percent)}", client=client,
                severity=Alert.Severity.CRITICAL if used >= 100 else Alert.Severity.WARNING,
                title=f"{client.name} has used {used:.0f}% of its monthly budget",
                body=f"{format_inr(spend.get(client.pk))} of {format_inr(client.monthly_budget_paise)} spent this month.",
                link="/billing/wallet/"))
    return alerts


def _campaign_daily(rule, today):
    percent = float(rule.params.get("percent", 100))
    yesterday = today - timedelta(days=1)
    spend = {r["campaign_id"]: r["s"] for r in MetricSnapshot.objects.filter(
        organization_id=rule.organization_id, date=yesterday).values("campaign_id").annotate(s=Sum("spend_paise"))}
    alerts = []
    for campaign in _campaigns(rule).filter(status=CampaignStatus.ACTIVE).exclude(daily_budget_paise__isnull=True):
        spent = spend.get(campaign.pk) or 0
        if campaign.daily_budget_paise and spent * 100 / campaign.daily_budget_paise >= percent:
            alerts.append(raise_alert(
                rule, key=f"campaign_daily:{campaign.pk}:{yesterday}", client=campaign.client,
                title=f"{campaign.name} spent {spent * 100 / campaign.daily_budget_paise:.0f}% of its daily budget",
                body=f"{format_inr(spent)} of {format_inr(campaign.daily_budget_paise)} on {yesterday:%d %b}.",
                link=f"/campaigns/{campaign.pk}/"))
    return alerts


def _high_cpl(rule, today):
    """Campaigns whose cost per lead over the window is above the limit: [(campaign, cpl_paise, spend)]."""
    limit = int(float(rule.params.get("cpl_rupees", 0)) * 100)
    days = int(rule.params.get("days", 7))
    if limit <= 0:
        return []
    rows = (_metrics(rule, today - timedelta(days=days)).values("campaign_id")
            .annotate(s=Sum("spend_paise"), l=Sum("leads")))
    campaigns = {c.pk: c for c in _campaigns(rule).filter(status=CampaignStatus.ACTIVE)}
    found = []
    for r in rows:
        campaign = campaigns.get(r["campaign_id"])
        if campaign and r["s"] and r["l"] and r["s"] / r["l"] > limit:
            found.append((campaign, r["s"] / r["l"], r["s"]))
        elif campaign and r["s"] and r["s"] > limit and not r["l"]:
            found.append((campaign, None, r["s"]))
    return found


def _cpl_above(rule, today):
    alerts = []
    for campaign, cpl, spend in _high_cpl(rule, today):
        cpl_text = format_inr(cpl) if cpl else "no leads"
        alerts.append(raise_alert(
            rule, key=f"cpl_above:{campaign.pk}:{today:%Y-%W}", client=campaign.client,
            title=f"{campaign.name}: cost per lead {cpl_text}",
            body=f"Limit ₹{rule.params.get('cpl_rupees')}. {format_inr(spend)} spent in the last {rule.params.get('days', 7)} days.",
            link=f"/campaigns/{campaign.pk}/"))
    return alerts


def _guarded_pause(rule, today):
    alerts = []
    for campaign, cpl, spend in _high_cpl(rule, today):
        if ActionRequest.objects.filter(campaign=campaign, status=ActionRequest.Status.PENDING).exists():
            continue
        cpl_text = format_inr(cpl) if cpl else "no leads"
        ActionRequest.objects.create(
            organization_id=rule.organization_id, client=campaign.client, campaign=campaign,
            action=ActionRequest.Action.PAUSE, source=ActionRequest.Source.RULE,
            reason=f"Rule “{rule.name}”: cost per lead {cpl_text} over the last {rule.params.get('days', 7)} days "
                   f"(limit ₹{rule.params.get('cpl_rupees')}, {format_inr(spend)} spent).")
        alerts.append(raise_alert(
            rule, key=f"guarded_pause:{campaign.pk}:{today}", client=campaign.client,
            title=f"Approval needed: pause {campaign.name}?", body=f"Cost per lead {cpl_text}.",
            link="/automation/approvals/"))
    return alerts


def _no_delivery(rule, today):
    days = int(rule.params.get("days", 2))
    since = today - timedelta(days=days)
    delivered = set(_metrics(rule, since).filter(impressions__gt=0).values_list("campaign_id", flat=True))
    alerts = []
    for campaign in _campaigns(rule).filter(status=CampaignStatus.ACTIVE):
        if campaign.pk not in delivered:
            alerts.append(raise_alert(
                rule, key=f"no_delivery:{campaign.pk}:{since}", client=campaign.client,
                severity=Alert.Severity.CRITICAL,
                title=f"{campaign.name} is active but had no impressions for {days} days",
                body="Check ad approvals, budget, payment method and targeting on the platform.",
                link=f"/campaigns/{campaign.pk}/"))
    return alerts


def _sync_failure(rule, today):
    accounts = AdAccount.objects.filter(organization_id=rule.organization_id,
                                        sync_status__in=[AdAccount.SyncStatus.FAILED, AdAccount.SyncStatus.PARTIAL])
    if rule.client_id:
        accounts = accounts.filter(client_id=rule.client_id)
    return [raise_alert(rule, key=f"sync_failure:{a.pk}:{a.last_synced_at or 'never'}", client=a.client,
                        severity=Alert.Severity.CRITICAL, title=f"Sync problem: {a.name}",
                        body=a.last_sync_error or a.get_sync_status_display(), link="/ads/accounts/")
            for a in accounts.select_related("client")]


def _approval_reminder(rule, today):
    days = int(rule.params.get("days", 2))
    cutoff = timezone.now() - timedelta(days=days)
    waiting = Creative.objects.filter(organization_id=rule.organization_id, updated_at__lte=cutoff,
                                      status__in=[Creative.Status.INTERNAL_REVIEW, Creative.Status.CLIENT_APPROVAL])
    if rule.client_id:
        waiting = waiting.filter(client_id=rule.client_id)
    alerts = [raise_alert(rule, key=f"approval:{c.pk}:{c.status}", client=c.client,
                          title=f"“{c.name}” has waited {days}+ days in {c.get_status_display().lower()}",
                          link=f"/creatives/{c.pk}/") for c in waiting.select_related("client")]
    pending = ActionRequest.objects.filter(organization_id=rule.organization_id, status=ActionRequest.Status.PENDING,
                                           created_at__lte=cutoff)
    if pending.exists():
        alerts.append(raise_alert(rule, key=f"approval_requests:{today}",
                                  title=f"{pending.count()} campaign change(s) waiting for approval",
                                  link="/automation/approvals/"))
    return alerts


def _scheduled_report(rule, today):
    frequency = rule.params.get("frequency", "weekly")
    due = today.weekday() == 0 if frequency == "weekly" else today.day == 1
    last = timezone.localtime(rule.last_run_at).date() if rule.last_run_at else None
    if not due or last == today or not rule.recipients:
        return []
    days = 7 if frequency == "weekly" else (today.replace(day=1) - timedelta(days=1)).day
    start, end = today - timedelta(days=days), today - timedelta(days=1)
    qs = MetricSnapshot.objects.filter(organization_id=rule.organization_id, date__gte=start, date__lte=end)
    if rule.client_id:
        qs = qs.filter(client_id=rule.client_id)
    totals = qs.aggregate(spend=Sum("spend_paise"), leads=Sum("leads"), clicks=Sum("clicks"), impr=Sum("impressions"))
    spend, leads = totals["spend"] or 0, totals["leads"] or 0
    by_platform = qs.values("platform").annotate(s=Sum("spend_paise"), l=Sum("leads")).order_by("-s")
    lines = [f"Camply {frequency} summary · {start:%d %b} to {end:%d %b %Y}",
             f"Scope: {rule.client.name if rule.client_id else 'all clients'}", "",
             f"Spend: {format_inr(spend)}", f"Leads: {leads}",
             f"Cost per lead: {format_inr(spend / leads) if leads else '–'}",
             f"Clicks: {totals['clicks'] or 0}  ·  Impressions: {totals['impr'] or 0}", "", "By platform:"]
    lines += [f"  {r['platform']}: {format_inr(r['s'])}, {r['l'] or 0} leads" for r in by_platform]
    lines += ["", "Figures as reported by each platform. INR, Asia/Kolkata."]
    send_mail(f"Camply {frequency} summary: {format_inr(spend)} spend, {leads} leads", "\n".join(lines),
              settings.DEFAULT_FROM_EMAIL, rule.recipients, fail_silently=True)
    return []


HANDLERS = {
    Rule.Kind.CLIENT_BUDGET: _client_budget,
    Rule.Kind.CAMPAIGN_DAILY: _campaign_daily,
    Rule.Kind.CPL_ABOVE: _cpl_above,
    Rule.Kind.NO_DELIVERY: _no_delivery,
    Rule.Kind.SYNC_FAILURE: _sync_failure,
    Rule.Kind.APPROVAL_REMINDER: _approval_reminder,
    Rule.Kind.GUARDED_PAUSE: _guarded_pause,
    Rule.Kind.SCHEDULED_REPORT: _scheduled_report,
}


def run_rule(rule, today=None):
    today = today or timezone.localdate()
    created = [a for a in HANDLERS[rule.kind](rule, today) if a is not None]
    rule.last_run_at = timezone.now()
    rule.save(update_fields=["last_run_at"])
    if created and rule.notify_email and rule.recipients:
        body = "\n\n".join(f"{a.title}\n{a.body}" for a in created)
        send_mail(f"Camply alert: {created[0].title}" + (f" (+{len(created) - 1} more)" if len(created) > 1 else ""),
                  body + "\n\nOpen Camply to review.", settings.DEFAULT_FROM_EMAIL, rule.recipients, fail_silently=True)
    return created


def run_rules(organization_id=None, today=None):
    rules = Rule.objects.filter(is_active=True).select_related("client")
    if organization_id:
        rules = rules.filter(organization_id=organization_id)
    created = []
    for rule in rules:
        try:
            created += run_rule(rule, today)
        except Exception:  # One broken rule must not stop the others.
            logger.exception("Automation rule %s failed", rule.pk)
    return created
