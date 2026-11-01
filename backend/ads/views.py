from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from audit import log as audit
from workspace.decorators import require_perm
from workspace.scoping import allowed_clients, ensure_client_allowed, get_scoped_or_404, scope

from .adapters import ADAPTERS, AdapterError, capabilities_for_account
from .adapters.base import CAPABILITY_LABELS
from .models import AdAccount, Platform, PlatformConnection
from .services import sync_account


@login_required
@require_perm("accounts.view")
def accounts(request):
    membership = request.membership
    qs = scope(AdAccount.objects.select_related("client", "connection"), membership, include_unassigned=True)
    platform = request.GET.get("platform", "")
    if platform in Platform.values:
        qs = qs.filter(platform=platform)
    rows = [{"account": a, "capabilities": [CAPABILITY_LABELS[c] for c in sorted(capabilities_for_account(a))]}
            for a in qs]
    return render(request, "ads/accounts.html", {
        "rows": rows,
        "platform": platform,
        "platforms": Platform.choices,
        "clients": allowed_clients(membership),
    })


@login_required
@require_POST
@require_perm("integrations.manage")
def sync_now(request, pk):
    account = get_scoped_or_404(AdAccount.objects.select_related("organization", "connection"),
                                request.membership, pk=pk)
    try:
        summary = sync_account(account, actor=request.user, request=request)
        messages.success(request, f"Synced {account.name}: {summary['campaigns']} campaigns, "
                                  f"{summary['rows']} days of results.")
    except AdapterError as exc:
        messages.error(request, f"Sync failed for {account.name}: {exc}")
    return redirect("ads:accounts")


@login_required
@require_POST
@require_perm("integrations.manage")
def assign_client(request, pk):
    membership = request.membership
    account = get_scoped_or_404(AdAccount.objects.all(), membership, pk=pk)
    client_id = request.POST.get("client") or None
    client = get_scoped_or_404(allowed_clients(membership), membership, client_field=None, pk=client_id) \
        if client_id else None
    ensure_client_allowed(membership, client)
    before = {"client": str(account.client) if account.client_id else None}
    account.client = client
    account.save(update_fields=["client"])
    # Keep denormalised client references in step so scoping stays correct.
    account.campaigns.update(client=client)
    account.metrics.update(client=client)
    audit.record(organization=account.organization, action="ad_account.assign_client", entity=account,
                 request=request, before=before, after={"client": str(client) if client else None})
    messages.success(request, f"{account.name} is now assigned to {client or 'no client'}.")
    return redirect("ads:accounts")


@login_required
@require_perm("accounts.view")
def integrations(request):
    connections = scope(PlatformConnection.objects.all(), request.membership, client_field=None)
    cards = []
    for platform in Platform:
        adapter_cls = ADAPTERS[platform]
        platform_connections = [c for c in connections if c.platform == platform]
        cards.append({
            "platform": platform,
            "connections": platform_connections,
            "available": bool(adapter_cls.capabilities),
            "capabilities": [CAPABILITY_LABELS[c] for c in sorted(adapter_cls.capabilities)],
            "docs_url": adapter_cls.docs_url,
            "account_count": scope(AdAccount.objects.filter(platform=platform), request.membership,
                                   include_unassigned=True).count(),
        })
    return render(request, "ads/integrations.html", {"cards": cards})
