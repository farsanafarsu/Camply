import csv
import json
from datetime import timedelta

from bson import ObjectId
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import User
from ads.models import AdAccount, Campaign, CampaignStatus, MetricSnapshot, Platform
from audit import log as audit
from workspace.decorators import require_perm
from workspace.models import Membership
from workspace.permissions import has_perm
from workspace.scoping import allowed_clients, ensure_client_allowed, get_scoped_or_404, scope

from .forms import LeadForm, LeadUpdateForm
from .models import Lead, LeadNote, LeadWebhook, find_duplicate, normalise_phone


def _team(organization):
    ids = Membership.objects.filter(organization=organization).values_list("user_id", flat=True)
    return User.objects.filter(pk__in=list(ids), is_active=True).order_by("first_name", "email")


@login_required
@require_perm("leads.view")
def inbox(request):
    membership = request.membership
    leads = scope(Lead.objects.select_related("client", "campaign", "assigned_to"), membership)
    status = request.GET.get("status", "")
    if status in Lead.Status.values:
        leads = leads.filter(status=status)
    client_id = request.GET.get("client", "")
    if ObjectId.is_valid(client_id):
        leads = leads.filter(client_id=client_id)
    if request.GET.get("mine"):
        leads = leads.filter(assigned_to=request.user)
    q = request.GET.get("q", "").strip()[:100]
    if q:
        from django.db.models import Q

        leads = leads.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
    counts = {r["status"]: r["n"] for r in scope(Lead.objects.all(), membership)
              .values("status").annotate(n=Count("pk"))}
    pipeline = [{"value": s.value, "label": s.label, "count": counts.get(s.value, 0)} for s in Lead.Status]
    due = scope(Lead.objects.filter(remind_at__lte=timezone.now(), assigned_to=request.user)
                .exclude(status__in=[Lead.Status.WON, Lead.Status.LOST, Lead.Status.INVALID]), membership)
    return render(request, "leads/inbox.html", {
        "leads": leads[:300], "pipeline": pipeline, "status": status, "q": q,
        "clients": allowed_clients(membership), "client_id": client_id, "due": due[:10],
    })


@login_required
@require_perm("leads.manage")
def add(request):
    membership = request.membership
    clients = allowed_clients(membership)
    campaigns = scope(Campaign.objects.all(), membership)
    form = LeadForm(request.POST or None, clients=clients, campaigns=campaigns)
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        ensure_client_allowed(membership, lead.client)
        lead.organization = request.organization
        lead.phone = normalise_phone(lead.phone) if lead.phone else ""
        lead.value_paise = form.cleaned_data.get("value")
        lead.platform = lead.campaign.platform if lead.campaign else ""
        lead.duplicate_of = find_duplicate(lead)
        lead.save()
        audit.record(organization=request.organization, action="lead.create", entity=lead, request=request)
        messages.success(request, "Lead added." + (" It looks like a duplicate of an earlier lead." if lead.duplicate_of else ""))
        return redirect("leads:detail", pk=lead.pk)
    return render(request, "leads/form.html", {"form": form})


@login_required
@require_perm("leads.view")
def detail(request, pk):
    membership = request.membership
    lead = get_scoped_or_404(Lead.objects.select_related("client", "campaign", "assigned_to", "duplicate_of"),
                             membership, pk=pk)
    can_manage = has_perm(membership, "leads.manage")
    form = LeadUpdateForm(
        request.POST or None, people=_team(request.organization),
        initial={"status": lead.status, "assigned_to": str(lead.assigned_to_id or ""),
                 "value": lead.value_paise / 100 if lead.value_paise else None,
                 "remind_at": timezone.localtime(lead.remind_at).strftime("%Y-%m-%dT%H:%M") if lead.remind_at else ""},
    )
    if request.method == "POST":
        if not can_manage:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        if "note" in request.POST:
            body = request.POST.get("note", "").strip()
            if body:
                LeadNote.objects.create(lead=lead, author=request.user, body=body[:4000])
                messages.success(request, "Note added.")
            return redirect("leads:detail", pk=lead.pk)
        if form.is_valid():
            before = {"status": lead.status, "assigned_to": str(lead.assigned_to or "")}
            lead.status = form.cleaned_data["status"]
            lead.assigned_to = form.cleaned_data["assigned_to"]
            lead.value_paise = form.cleaned_data.get("value")
            lead.remind_at = form.cleaned_data.get("remind_at")
            lead.save()
            audit.record(organization=request.organization, action="lead.update", entity=lead, request=request,
                         before=before, after={"status": lead.status, "assigned_to": str(lead.assigned_to or "")})
            messages.success(request, "Lead updated.")
            return redirect("leads:detail", pk=lead.pk)
    return render(request, "leads/detail.html", {
        "lead": lead, "form": form, "can_manage": can_manage, "notes": lead.notes.select_related("author"),
    })


@login_required
@require_perm("leads.view", "reports.export")
def export_csv(request):
    leads = scope(Lead.objects.select_related("client", "campaign", "assigned_to"), request.membership)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="camply-leads-{timezone.localdate()}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(["Received (IST)", "Client", "Name", "Email", "Phone", "City", "Status", "Assigned to",
                     "Campaign", "Platform", "Source", "Consent", "UTM source", "UTM medium", "UTM campaign",
                     "Deal value (INR)", "Duplicate"])
    for lead in leads:
        writer.writerow([
            timezone.localtime(lead.created_at).strftime("%Y-%m-%d %H:%M"), lead.client.name, lead.full_name,
            lead.email, lead.phone, lead.city, lead.get_status_display(),
            lead.assigned_to.display_name if lead.assigned_to else "", lead.campaign.name if lead.campaign else "",
            lead.platform, lead.get_source_display(), "yes" if lead.consent else "no", lead.utm_source,
            lead.utm_medium, lead.utm_campaign, f"{lead.value_paise / 100:.2f}" if lead.value_paise else "",
            "yes" if lead.duplicate_of_id else "",
        ])
    return response


@login_required
@require_perm("leads.manage")
def sources(request):
    """Website-form webhooks, one secret URL per client."""
    membership = request.membership
    clients = list(allowed_clients(membership))
    if request.method == "POST":
        client = get_scoped_or_404(allowed_clients(membership), membership, client_field=None,
                                   pk=request.POST.get("client", ""))
        LeadWebhook.objects.filter(client=client).delete()
        LeadWebhook.objects.create(organization=request.organization, client=client)
        audit.record(organization=request.organization, action="lead.webhook_reset", entity=client, request=request)
        messages.success(request, f"New form URL created for {client.name}. Update your website form to use it.")
        return redirect("leads:sources")
    hooks = {h.client_id: h for h in LeadWebhook.objects.filter(client_id__in=[c.pk for c in clients])}
    rows = [{"client": c, "hook": hooks.get(c.pk),
             "url": request.build_absolute_uri(f"/leads/in/{hooks[c.pk].token}/") if c.pk in hooks else ""}
            for c in clients]
    return render(request, "leads/sources.html", {"rows": rows})


@csrf_exempt
@require_POST
def webhook(request, token):
    """Public endpoint for website forms. Accepts form-encoded or JSON bodies."""
    hook = LeadWebhook.objects.select_related("client").filter(token=token).first()
    if hook is None:
        raise Http404
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    else:
        data = request.POST
    get = lambda *keys: next((str(data.get(k)).strip() for k in keys if data.get(k)), "")  # noqa: E731
    email, phone = get("email")[:254], normalise_phone(get("phone", "mobile", "tel"))
    if not (email or phone):
        return JsonResponse({"ok": False, "error": "Send an email or phone"}, status=400)
    lead = Lead(
        organization_id=hook.organization_id, client=hook.client, source=Lead.Source.WEBHOOK,
        full_name=get("name", "full_name")[:150], email=email, phone=phone, city=get("city")[:80],
        message=get("message", "comments")[:4000],
        consent=get("consent").lower() in {"1", "true", "yes", "on"},
        utm_source=get("utm_source")[:100], utm_medium=get("utm_medium")[:100],
        utm_campaign=get("utm_campaign")[:150], utm_content=get("utm_content")[:150], utm_term=get("utm_term")[:150],
    )
    lead.duplicate_of = find_duplicate(lead)
    lead.save()
    redirect_to = get("redirect")
    if redirect_to.startswith("https://"):
        return redirect(redirect_to)
    return JsonResponse({"ok": True})


@login_required
@require_perm("leads.view")
def utm_builder(request):
    return render(request, "leads/utm.html", {"platforms": Platform.choices})


@login_required
@require_perm("leads.view")
def tracking(request):
    """Tracking health: campaigns spending without conversions, accounts with sync problems."""
    membership = request.membership
    since = timezone.localdate() - timedelta(days=7)
    rows = (scope(MetricSnapshot.objects.filter(date__gte=since), membership)
            .values("campaign_id").annotate(spend=Sum("spend_paise"), clicks=Sum("clicks"), conv=Sum("conversions")))
    silent_ids = [r["campaign_id"] for r in rows if r["spend"] and r["spend"] >= 100000 and not r["conv"]]
    spend = {r["campaign_id"]: r for r in rows}
    silent = [{"campaign": c, **spend[c.pk]} for c in
              Campaign.objects.filter(pk__in=silent_ids).select_related("client")]
    unhealthy = scope(AdAccount.objects.exclude(sync_status__in=[AdAccount.SyncStatus.OK, AdAccount.SyncStatus.MANUAL]),
                      membership, include_unassigned=True)
    active_no_leads = scope(Campaign.objects.filter(status=CampaignStatus.ACTIVE), membership).count()
    return render(request, "leads/tracking.html", {
        "silent": silent, "unhealthy": unhealthy, "active_count": active_no_leads, "checklist": CHECKLIST,
    })


CHECKLIST = {
    "Meta Ads": ["Meta Pixel installed on every page", "Conversions API connected (server events)",
                 "Lead and Purchase standard events firing", "Event match quality 'Good' or better",
                 "Domain verified in Business Manager"],
    "Google Ads": ["Google tag (gtag.js) or Tag Manager on every page", "Conversion actions created and recording",
                   "Enhanced conversions turned on", "Auto-tagging (gclid) enabled",
                   "Offline conversions imported for qualified leads"],
    "TikTok Ads": ["TikTok Pixel installed", "Events API connected", "Submit form / Complete payment events firing"],
    "ChatGPT Ads": ["Landing pages tagged with UTM parameters", "Conversions tracked in your analytics tool"],
}
