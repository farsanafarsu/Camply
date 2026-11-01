"""Platform admin console: Camply-wide view of every agency and user, for superusers only.

Unlike the agency workspace, nothing here is scoped to an organization. Access is limited
to active superusers by `platform_admin_required`.
"""

import logging
from datetime import timedelta
from functools import wraps

from allauth.mfa.models import Authenticator
from bson import ObjectId
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from ads.models import AdAccount, Campaign
from workspace.models import Client, Membership, Organization

logger = logging.getLogger("camply.console")


def platform_admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_active and request.user.is_superuser):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def _counts_by_org(model):
    return {r["organization_id"]: r["n"] for r in model.objects.values("organization_id").annotate(n=Count("pk"))}


def _agency_rows(organizations):
    members = _counts_by_org(Membership)
    clients = _counts_by_org(Client)
    accounts = _counts_by_org(AdAccount)
    return [
        {
            "org": org,
            "members": members.get(org.pk, 0),
            "clients": clients.get(org.pk, 0),
            "ad_accounts": accounts.get(org.pk, 0),
        }
        for org in organizations
    ]


def _memberships_by_user(user_ids):
    rows = {}
    for m in Membership.objects.filter(user_id__in=user_ids).select_related("organization"):
        rows.setdefault(m.user_id, []).append(m)
    return rows


@platform_admin_required
def overview(request):
    month_ago = timezone.now() - timedelta(days=30)
    stats = {
        "agencies": Organization.objects.count(),
        "users": User.objects.count(),
        "active_users": User.objects.filter(last_login__gte=month_ago).count(),
        "clients": Client.objects.count(),
        "ad_accounts": AdAccount.objects.count(),
        "campaigns": Campaign.objects.count(),
    }
    recent_users = list(User.objects.order_by("-date_joined")[:6])
    return render(request, "console/overview.html", {
        "stats": stats,
        "recent_agencies": _agency_rows(Organization.objects.order_by("-created_at")[:6]),
        "recent_users": recent_users,
        "user_memberships": _memberships_by_user([u.pk for u in recent_users]),
    })


@platform_admin_required
def agencies(request):
    q = request.GET.get("q", "").strip()[:100]
    orgs = Organization.objects.order_by("name")
    if q:
        orgs = orgs.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(gstin__icontains=q))
    return render(request, "console/agencies.html", {"rows": _agency_rows(orgs), "q": q})


@platform_admin_required
def agency_detail(request, pk):
    if not ObjectId.is_valid(pk):
        raise Http404
    org = get_object_or_404(Organization, pk=pk)
    members = list(Membership.objects.filter(organization=org).select_related("user").order_by("role"))
    return render(request, "console/agency_detail.html", {
        "org": org,
        "members": members,
        "clients": Client.objects.filter(organization=org),
        "ad_accounts": AdAccount.objects.filter(organization=org).select_related("client"),
        "campaign_count": Campaign.objects.filter(organization=org).count(),
    })


@platform_admin_required
def users(request):
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    qs = User.objects.order_by("-date_joined")
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if status == "admins":
        qs = qs.filter(is_superuser=True)
    elif status == "disabled":
        qs = qs.filter(is_active=False)
    people = list(qs[:300])
    ids = [u.pk for u in people]
    with_2fa = set(Authenticator.objects.filter(user_id__in=ids, type=Authenticator.Type.TOTP)
                   .values_list("user_id", flat=True))
    memberships = _memberships_by_user(ids)
    rows = [{"user": u, "memberships": memberships.get(u.pk, []), "two_factor": u.pk in with_2fa} for u in people]
    return render(request, "console/users.html", {"rows": rows, "q": q, "status": status})


@require_POST
@platform_admin_required
def user_status(request, pk):
    if not ObjectId.is_valid(pk):
        raise Http404
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "You can't disable your own account.")
        return redirect("console:users")
    target.is_active = request.POST.get("action") == "enable"
    target.save(update_fields=["is_active"])
    verb = "enabled" if target.is_active else "disabled"
    logger.info("Platform admin %s %s user %s", request.user.email, verb, target.email)
    messages.success(request, f"{target.email} is now {verb}."
                     + ("" if target.is_active else " They can no longer sign in."))
    return redirect("console:users")
