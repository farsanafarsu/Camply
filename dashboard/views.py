import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ads.adapters import AdapterError, Capability, capabilities_for_account
from ads.adapters.base import CAPABILITY_LABELS
from ads.models import Campaign, CampaignStatus, MetricSnapshot, Platform
from ads.services import set_campaign_status
from audit.models import AuditEvent
from workspace.decorators import require_perm
from workspace.scoping import allowed_clients, get_scoped_or_404, scope

from . import analytics


def filter_context(request):
    filters = analytics.parse_filters(request.GET)
    return filters, {
        "filters": filters,
        "presets": analytics.PRESETS,
        "platforms": Platform.choices,
        "filter_clients": allowed_clients(request.membership),
    }


@login_required
@require_perm("dashboard.view")
def home(request):
    membership = request.membership
    filters, ctx = filter_context(request)
    breakdown, total_spend = analytics.platform_breakdown(membership, filters)
    ctx.update({
        "kpis": analytics.kpis(membership, filters),
        "trend": analytics.spend_trend(membership, filters),
        "breakdown": breakdown,
        "total_spend": total_spend,
        "donut": [{"label": p["label"], "value": round(p["spend_paise"] / 100), "color": p["color"]}
                  for p in breakdown],
        "recent_campaigns": analytics.campaign_rows(membership, filters, limit=6),
        "active_campaigns": analytics.active_campaign_count(membership, filters),
        "freshness": analytics.data_freshness(membership),
        "activity": scope(AuditEvent.objects.select_related("actor"), membership, include_unassigned=True)[:6],
    })
    return render(request, "dashboard/home.html", ctx)


CAMPAIGN_SORTS = {
    "spend": "-spend_paise", "leads": "-leads", "cpl": "cpl_paise", "roas": "-roas", "name": "name",
}


@login_required
@require_perm("campaigns.view")
def campaigns(request):
    filters, ctx = filter_context(request)
    status = request.GET.get("status", "")
    if status not in CampaignStatus.values:
        status = ""
    sort = request.GET.get("sort", "spend")
    rows = analytics.campaign_rows(
        request.membership, filters, status=status, search=request.GET.get("q", "").strip()[:100],
        order=CAMPAIGN_SORTS.get(sort, "-spend_paise"),
    )
    ctx.update({"rows": rows, "status": status, "statuses": CampaignStatus.choices, "sort": sort,
                "q": request.GET.get("q", "")})
    return render(request, "dashboard/campaigns.html", ctx)


@login_required
@require_perm("campaigns.view")
def campaign_detail(request, pk):
    campaign = get_scoped_or_404(
        Campaign.objects.select_related("client", "ad_account", "ad_account__connection"), request.membership, pk=pk
    )
    filters, ctx = filter_context(request)
    metrics = MetricSnapshot.objects.filter(campaign=campaign, date__gte=filters.start, date__lte=filters.end)
    caps = capabilities_for_account(campaign.ad_account)
    ctx.update({
        "campaign": campaign,
        "series": analytics.daily_series(metrics, filters.start, filters.end),
        "totals": analytics.derive(analytics._totals(metrics)),
        "ad_sets": campaign.ad_sets.all(),
        "history": AuditEvent.objects.filter(
            organization_id=campaign.organization_id, entity_type="campaign", entity_id=str(campaign.pk)
        )[:20],
        "can_pause": Capability.PAUSE in caps and campaign.status == CampaignStatus.ACTIVE,
        "can_resume": Capability.RESUME in caps and campaign.status == CampaignStatus.PAUSED,
        "capabilities": [CAPABILITY_LABELS[c] for c in sorted(caps)],
    })
    return render(request, "dashboard/campaign_detail.html", ctx)


@login_required
@require_POST
@require_perm("campaigns.edit")
def campaign_status(request, pk):
    campaign = get_scoped_or_404(Campaign.objects.select_related("ad_account"), request.membership, pk=pk)
    action = request.POST.get("action")
    target = {"pause": CampaignStatus.PAUSED, "resume": CampaignStatus.ACTIVE}.get(action)
    if target is None:
        messages.error(request, "Unknown action.")
    else:
        try:
            set_campaign_status(campaign, target, actor=request.user, request=request)
            messages.success(request, f"{campaign.name} is now {CampaignStatus(target).label.lower()}.")
        except AdapterError as exc:
            messages.error(request, f"{campaign.get_platform_display()} did not accept the change: {exc}")
    return redirect("dashboard:campaign_detail", pk=campaign.pk)


@login_required
@require_perm("reports.view")
def reports(request):
    filters, ctx = filter_context(request)
    membership = request.membership
    breakdown, total_spend = analytics.platform_breakdown(membership, filters)
    ctx.update({
        "kpis": analytics.kpis(membership, filters),
        "breakdown": breakdown,
        "total_spend": total_spend,
        "rows": analytics.campaign_rows(membership, filters),
        "freshness": analytics.data_freshness(membership),
    })
    return render(request, "dashboard/reports.html", ctx)


@login_required
@require_perm("reports.export")
def reports_csv(request):
    filters = analytics.parse_filters(request.GET)
    rows = analytics.campaign_rows(request.membership, filters)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"camply-report-{filters.start}-to-{filters.end}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM so Excel reads ₹ correctly
    writer = csv.writer(response)
    writer.writerow([f"Camply cross-channel report · {filters.start} to {filters.end} · INR · Asia/Kolkata"])
    writer.writerow(["Campaign", "Client", "Platform", "Status", "Spend (INR)", "Impressions", "Clicks", "Leads",
                     "CPL (INR)", "CTR %", "ROAS"])
    for r in rows:
        c = r["campaign"]
        writer.writerow([
            c.name, c.client.name if c.client else "", c.get_platform_display(), c.get_status_display(),
            f"{r['spend_paise'] / 100:.2f}", r["impressions"], r["clicks"], r["leads"],
            f"{r['cpl_paise'] / 100:.2f}" if r["cpl_paise"] is not None else "",
            f"{r['ctr']:.2f}" if r["ctr"] is not None else "",
            f"{r['roas']:.2f}" if r["roas"] is not None else "",
        ])
    writer.writerow([])
    writer.writerow(["Figures are as reported by each platform. CPL = spend ÷ leads. "
                     "ROAS only where revenue tracking is connected."])
    return response


@login_required
@require_perm("audit.view")
def audit_log(request):
    events = scope(AuditEvent.objects.select_related("actor", "client"), request.membership, include_unassigned=True)
    return render(request, "dashboard/audit_log.html", {"events": events[:200]})


PLANNED = {
    "creatives": ("Creative Studio", "creatives.view", "Phase 3",
                  "A shared library for images, videos and ad copy, tagged by client and platform, with an "
                  "approval flow: Draft → Internal review → Client approval → Ready to publish."),
    "leads": ("Leads", "leads.view", "Phase 3",
              "One inbox for leads from Meta lead forms, Google lead forms and website conversions, with a "
              "status pipeline (New → Contacted → Qualified → Won) and CSV export."),
    "automation": ("Automation", "automation.manage", "Phase 4",
                   "Rules such as “alert me when spend reaches 80% of budget” or “flag campaigns with no "
                   "delivery”. Any change to spend or status waits for a person to approve it."),
    "copilot": ("AI Copilot", "copilot.use", "Phase 4",
                "Ask questions about your synced campaign data in plain language, get plain-English client "
                "summaries and suggested next steps. Suggestions never change campaigns without approval."),
}


@login_required
def planned(request, section):
    title, perm, phase, description = PLANNED[section]
    return require_perm(perm)(lambda r: render(r, "dashboard/planned.html", {
        "title": title, "phase": phase, "description": description,
    }))(request)


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)
