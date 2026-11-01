"""Cross-channel metrics. Every function here takes a membership and scopes its queries."""

from dataclasses import dataclass
from datetime import date, timedelta

import time

from bson import ObjectId
from django.core.cache import cache
from django.db.models import Count, Max, Sum
from django.utils import timezone

from ads.models import AdAccount, Campaign, CampaignStatus, MetricSnapshot, Platform
from camply.money import safe_ratio
from workspace.scoping import scope

SUM_FIELDS = ("spend_paise", "impressions", "clicks", "leads", "conversions", "revenue_paise")

PLATFORM_COLORS = {
    # Categorical chart colours chosen to stay distinguishable in light and dark mode.
    Platform.META: "#3B82F6",
    Platform.GOOGLE: "#FF9F43",
    Platform.TIKTOK: "#E8467C",
    Platform.OPENAI: "#8B5CF6",
}


@dataclass
class Filters:
    start: date
    end: date
    platform: str = ""
    client_id: str = ""
    preset: str = "30d"

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def previous(self):
        end = self.start - timedelta(days=1)
        return Filters(start=end - timedelta(days=self.days - 1), end=end, platform=self.platform,
                       client_id=self.client_id)


PRESETS = {
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "90d": "Last 90 days",
    "mtd": "This month",
    "last_month": "Last month",
}


CACHE_SECONDS = 120


def _version_key(organization_id):
    return f"analytics-version:{organization_id}"


def invalidate(organization_id):
    """Call when an agency's campaigns or results change (sync, pause, budget)."""
    cache.set(_version_key(organization_id), time.time(), None)


def cached(membership, filters: "Filters", name, compute):
    """Cache a page's analytics briefly per person, agency and filter.

    Results only change when accounts sync or campaigns are edited, which bump the
    agency's version (see invalidate), so a stale answer never outlives a change.
    """
    version = cache.get(_version_key(membership.organization_id), 0)
    key = ":".join(str(part) for part in (
        "analytics", name, version, membership.organization_id, membership.user_id, membership.role,
        filters.start, filters.end, filters.platform, filters.client_id,
    ))
    value = cache.get(key)
    if value is None:
        value = compute()
        cache.set(key, value, CACHE_SECONDS)
    return value


def parse_filters(params) -> Filters:
    today = timezone.localdate()
    preset = params.get("range", "30d")
    platform = params.get("platform", "")
    if platform not in Platform.values:
        platform = ""
    client_id = params.get("client", "")
    if not ObjectId.is_valid(client_id):
        client_id = ""
    if preset == "custom":
        try:
            start = date.fromisoformat(params.get("start", ""))
            end = date.fromisoformat(params.get("end", ""))
            if start > end:
                start, end = end, start
            end = min(end, today)
            start = max(start, end - timedelta(days=366))
            return Filters(start, end, platform, client_id, "custom")
        except ValueError:
            preset = "30d"
    if preset == "7d":
        start, end = today - timedelta(days=6), today
    elif preset == "90d":
        start, end = today - timedelta(days=89), today
    elif preset == "mtd":
        start, end = today.replace(day=1), today
    elif preset == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    else:
        preset = "30d"
        start, end = today - timedelta(days=29), today
    return Filters(start, end, platform, client_id, preset)


def metrics_qs(membership, filters: Filters):
    qs = scope(MetricSnapshot.objects.all(), membership).filter(date__gte=filters.start, date__lte=filters.end)
    if filters.platform:
        qs = qs.filter(platform=filters.platform)
    if filters.client_id:
        qs = qs.filter(client_id=filters.client_id)
    return qs


def _totals(qs):
    agg = qs.aggregate(**{f: Sum(f) for f in SUM_FIELDS})
    totals = {f: agg[f] or 0 for f in SUM_FIELDS}
    # Revenue is only meaningful for rows that track it; spend for ROAS uses the same rows.
    tracked = qs.filter(revenue_paise__isnull=False).aggregate(spend=Sum("spend_paise"), revenue=Sum("revenue_paise"))
    totals["roas_spend_paise"] = tracked["spend"] or 0
    totals["revenue_paise"] = tracked["revenue"] or 0
    return totals


def derive(totals):
    """Weighted ratios computed from summed totals (never averages of averages)."""
    spend = totals["spend_paise"]
    return {
        **totals,
        "cpl_paise": safe_ratio(spend, totals["leads"]),
        "cpc_paise": safe_ratio(spend, totals["clicks"]),
        "cpm_paise": safe_ratio(spend * 1000, totals["impressions"]),
        "ctr": safe_ratio(totals["clicks"] * 100, totals["impressions"]),
        "roas": safe_ratio(totals["revenue_paise"], totals["roas_spend_paise"])
        if totals["roas_spend_paise"]
        else None,
    }


def change(current, previous):
    if current is None or not previous:
        return None
    return (current - previous) * 100 / previous


def kpis(membership, filters: Filters):
    current = derive(_totals(metrics_qs(membership, filters)))
    previous = derive(_totals(metrics_qs(membership, filters.previous())))
    keys = ("spend_paise", "leads", "impressions", "clicks", "cpl_paise", "roas", "ctr")
    current["change"] = {k: change(current[k], previous[k]) for k in keys}
    current["roas_delta"] = (
        round(current["roas"] - previous["roas"], 1)
        if current["roas"] is not None and previous["roas"] is not None
        else None
    )
    return current


def spend_trend(membership, filters: Filters):
    """Daily spend per platform for the line chart: {labels: [...], series: [{platform, label, color, data}]}."""
    rows = metrics_qs(membership, filters).values("date", "platform").annotate(spend=Sum("spend_paise"))
    by_key = {(r["date"], r["platform"]): r["spend"] for r in rows}
    days = [filters.start + timedelta(days=i) for i in range(filters.days)]
    platforms = [p for p in Platform if not filters.platform or p == filters.platform]
    series = []
    for p in platforms:
        data = [round((by_key.get((d, p.value)) or 0) / 100) for d in days]
        if any(data):
            series.append({"platform": p.value, "label": p.label, "color": PLATFORM_COLORS[p], "data": data})
    return {"labels": [d.isoformat() for d in days], "series": series}


def platform_breakdown(membership, filters: Filters):
    qs = metrics_qs(membership, filters)
    rows = {r["platform"]: r for r in qs.values("platform").annotate(**{f: Sum(f) for f in SUM_FIELDS})}
    total_spend = sum((r["spend_paise"] or 0) for r in rows.values())
    result = []
    for p in Platform:
        r = rows.get(p.value)
        if not r:
            continue
        spend = r["spend_paise"] or 0
        result.append({
            "platform": p.value,
            "label": p.label,
            "color": PLATFORM_COLORS[p],
            "spend_paise": spend,
            "share": safe_ratio(spend * 100, total_spend) or 0,
            "leads": r["leads"] or 0,
            "clicks": r["clicks"] or 0,
            "impressions": r["impressions"] or 0,
            "cpl_paise": safe_ratio(spend, r["leads"]),
        })
    result.sort(key=lambda r: r["spend_paise"], reverse=True)
    return result, total_spend


def campaign_rows(membership, filters: Filters, *, status="", search="", order="-spend_paise", limit=None):
    """Campaigns with their totals for the period, as dicts ready for tables."""
    campaigns = scope(Campaign.objects.select_related("client", "ad_account"), membership)
    if filters.platform:
        campaigns = campaigns.filter(platform=filters.platform)
    if filters.client_id:
        campaigns = campaigns.filter(client_id=filters.client_id)
    if status:
        campaigns = campaigns.filter(status=status)
    if search:
        campaigns = campaigns.filter(name__icontains=search)
    campaigns = list(campaigns)
    ids = [c.pk for c in campaigns]
    stats = {
        r["campaign_id"]: r
        for r in metrics_qs(membership, filters).filter(campaign_id__in=ids)
        .values("campaign_id").annotate(**{f: Sum(f) for f in SUM_FIELDS})
    }
    tracked = {
        r["campaign_id"]: r
        for r in metrics_qs(membership, filters).filter(campaign_id__in=ids, revenue_paise__isnull=False)
        .values("campaign_id").annotate(spend=Sum("spend_paise"), revenue=Sum("revenue_paise"))
    }
    rows = []
    for c in campaigns:
        s = stats.get(c.pk, {})
        t = tracked.get(c.pk)
        spend = s.get("spend_paise") or 0
        rows.append({
            "campaign": c,
            "spend_paise": spend,
            "impressions": s.get("impressions") or 0,
            "clicks": s.get("clicks") or 0,
            "leads": s.get("leads") or 0,
            "cpl_paise": safe_ratio(spend, s.get("leads")),
            "ctr": safe_ratio((s.get("clicks") or 0) * 100, s.get("impressions")),
            "roas": safe_ratio(t["revenue"], t["spend"]) if t and t["spend"] else None,
        })
    reverse = order.startswith("-")
    key = order.lstrip("-")
    if key == "name":
        rows.sort(key=lambda r: r["campaign"].name.lower(), reverse=reverse)
    else:
        # Rows without a value (e.g. no ROAS) always go last, whichever direction.
        present = sorted((r for r in rows if r.get(key) is not None), key=lambda r: r[key], reverse=reverse)
        rows = present + [r for r in rows if r.get(key) is None]
    return rows[:limit] if limit else rows


def daily_series(qs, start, end):
    rows = {r["date"]: r for r in qs.values("date").annotate(spend=Sum("spend_paise"), leads=Sum("leads"),
                                                              clicks=Sum("clicks"))}
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return {
        "labels": [d.isoformat() for d in days],
        "spend": [round((rows.get(d, {}).get("spend") or 0) / 100) for d in days],
        "leads": [rows.get(d, {}).get("leads") or 0 for d in days],
    }


def active_campaign_count(membership, filters: Filters):
    qs = scope(Campaign.objects.filter(status=CampaignStatus.ACTIVE), membership)
    if filters.platform:
        qs = qs.filter(platform=filters.platform)
    if filters.client_id:
        qs = qs.filter(client_id=filters.client_id)
    return qs.count()


def data_freshness(membership):
    accounts = scope(AdAccount.objects.all(), membership)
    agg = accounts.aggregate(last=Max("last_synced_at"), n=Count("pk"))
    unhealthy = accounts.filter(sync_status__in=[AdAccount.SyncStatus.FAILED, AdAccount.SyncStatus.PARTIAL])
    return {"last_synced_at": agg["last"], "accounts": agg["n"], "unhealthy": list(unhealthy[:5])}
