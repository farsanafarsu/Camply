from bson import ObjectId
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit import log as audit

from .decorators import require_perm
from .forms import ClientForm, InviteForm, MemberAccessForm, OrganizationForm
from .middleware import SESSION_KEY
from .models import Client, Invitation, Membership, Role
from .permissions import ASSIGNABLE_ROLES, has_perm, permission_matrix
from .scoping import allowed_clients, get_scoped_or_404


@login_required
def onboarding(request):
    if request.membership is not None:
        return redirect("dashboard:home")
    pending = Invitation.objects.filter(email__iexact=request.user.email, accepted_at__isnull=True,
                                        expires_at__gt=timezone.now()).select_related("organization")
    form = OrganizationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        org = form.save()
        Membership.objects.create(organization=org, user=request.user, role=Role.OWNER, all_clients=True)
        request.session[SESSION_KEY] = str(org.pk)
        audit.record(organization=org, action="organization.create", entity=org, request=request)
        messages.success(request, f"Welcome to Camply. {org.name} is ready — add your first client next.")
        return redirect("workspace:clients")
    return render(request, "workspace/onboarding.html", {"form": form, "pending": pending})


@login_required
@require_POST
def switch_organization(request):
    org_id = request.POST.get("organization", "")
    membership = Membership.objects.filter(user=request.user, organization_id=org_id).first() \
        if ObjectId.is_valid(org_id) else None
    if membership is None:
        raise PermissionDenied
    request.session[SESSION_KEY] = str(membership.organization_id)
    return redirect("dashboard:home")


@login_required
@require_perm("dashboard.view")
def clients(request):
    form = None
    if has_perm(request.membership, "clients.manage"):
        form = ClientForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            client = form.save(commit=False)
            client.organization = request.organization
            form.save()
            audit.record(organization=request.organization, action="client.create", entity=client, request=request)
            messages.success(request, f"Client {client.name} added.")
            return redirect("workspace:clients")
    elif request.method == "POST":
        raise PermissionDenied
    return render(request, "workspace/clients.html", {
        "clients": allowed_clients(request.membership),
        "form": form,
    })


@login_required
@require_perm("clients.manage")
def client_edit(request, pk):
    client = get_scoped_or_404(allowed_clients(request.membership), request.membership, client_field=None, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.record(organization=request.organization, action="client.update", entity=client, request=request)
        messages.success(request, f"{client.name} updated.")
        return redirect("workspace:clients")
    return render(request, "workspace/client_edit.html", {"form": form, "client": client})


def _assignable(membership):
    return ASSIGNABLE_ROLES.get(membership.role, [])


@login_required
@require_perm("dashboard.view")
def team(request):
    membership = request.membership
    can_manage = has_perm(membership, "team.manage")
    org_clients = list(Client.objects.filter(organization=request.organization))
    roles, matrix = permission_matrix()
    return render(request, "workspace/team.html", {
        "members": Membership.objects.filter(organization=request.organization)
        .select_related("user"),
        "invitations": [i for i in Invitation.objects.filter(organization=request.organization,
                                                             accepted_at__isnull=True) if i.is_pending],
        "invite_form": InviteForm(assignable_roles=_assignable(membership), clients=org_clients)
        if can_manage else None,
        "roles": roles,
        "matrix": matrix,
        "can_manage": can_manage,
    })


@login_required
@require_POST
@require_perm("team.manage")
def invite(request):
    membership = request.membership
    org_clients = list(Client.objects.filter(organization=request.organization))
    form = InviteForm(request.POST, assignable_roles=_assignable(membership), clients=org_clients)
    if not form.is_valid():
        messages.error(request, "Could not send the invite: " + "; ".join(
            f"{k}: {' '.join(v)}" for k, v in form.errors.items()))
        return redirect("workspace:team")
    data = form.cleaned_data
    if Membership.objects.filter(organization=request.organization, user__email__iexact=data["email"]).exists():
        messages.info(request, f"{data['email']} is already a member.")
        return redirect("workspace:team")
    invitation = Invitation.objects.create(
        organization=request.organization, email=data["email"].lower(), role=data["role"],
        all_clients=data["all_clients"], invited_by=request.user,
    )
    invitation.clients.set(data["clients"])
    link = request.build_absolute_uri(reverse("workspace:accept_invite", args=[invitation.token]))
    send_mail(
        subject=f"{request.user.display_name} invited you to {request.organization.name} on Camply",
        message=(f"You've been invited to join {request.organization.name} on Camply as "
                 f"{invitation.get_role_display()}.\n\nAccept the invitation: {link}\n\n"
                 "This link expires in 7 days."),
        from_email=None,
        recipient_list=[invitation.email],
    )
    audit.record(organization=request.organization, action="team.invite", entity=invitation, request=request,
                 after={"email": invitation.email, "role": invitation.role})
    messages.success(request, f"Invitation sent to {invitation.email}.")
    return redirect("workspace:team")


@login_required
def accept_invite(request, token):
    invitation = get_object_or_404(Invitation.objects.select_related("organization"), token=token)
    if not invitation.is_pending:
        raise Http404("This invitation has expired or was already used.")
    if invitation.email.lower() != request.user.email.lower():
        messages.error(request, f"This invitation is for {invitation.email}. Sign in with that email to accept it.")
        return redirect("dashboard:home" if request.membership else "workspace:onboarding")
    if request.method == "POST":
        membership, _ = Membership.objects.get_or_create(
            organization=invitation.organization, user=request.user,
            defaults={"role": invitation.role, "all_clients": invitation.all_clients},
        )
        membership.clients.set(invitation.clients.all())
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])
        request.session[SESSION_KEY] = str(invitation.organization_id)
        audit.record(organization=invitation.organization, action="team.join", entity=membership, request=request)
        messages.success(request, f"You've joined {invitation.organization.name}.")
        return redirect("dashboard:home")
    return render(request, "workspace/accept_invite.html", {"invitation": invitation})


@login_required
@require_perm("team.manage")
def member_edit(request, pk):
    membership = request.membership
    target = get_object_or_404(Membership.objects.select_related("user"), pk=pk,
                               organization=request.organization) if _valid_id(pk) else None
    if target is None:
        raise Http404
    assignable = _assignable(membership)
    if target.role not in assignable:
        raise PermissionDenied  # e.g. an admin cannot edit an owner
    org_clients = list(Client.objects.filter(organization=request.organization))
    initial = {"role": target.role, "all_clients": target.all_clients,
               "clients": [str(c.pk) for c in target.clients.all()]}
    form = MemberAccessForm(request.POST or None, initial=initial, assignable_roles=assignable, clients=org_clients)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if target.role == Role.OWNER and data["role"] != Role.OWNER and \
                not Membership.objects.filter(organization=request.organization, role=Role.OWNER) \
                .exclude(pk=target.pk).exists():
            messages.error(request, "An organization needs at least one owner.")
            return redirect("workspace:member_edit", pk=pk)
        before = {"role": target.role, "all_clients": target.all_clients}
        target.role = data["role"]
        target.all_clients = data["all_clients"]
        target.save(update_fields=["role", "all_clients"])
        target.clients.set(data["clients"])
        audit.record(organization=request.organization, action="team.update", entity=target, request=request,
                     before=before, after={"role": target.role, "all_clients": target.all_clients,
                                           "clients": [c.name for c in data["clients"]]})
        messages.success(request, f"Updated access for {target.user.display_name}.")
        return redirect("workspace:team")
    return render(request, "workspace/member_edit.html", {"form": form, "target": target})


@login_required
@require_perm("org.manage")
def settings_view(request):
    form = OrganizationForm(request.POST or None, instance=request.organization)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.record(organization=request.organization, action="organization.update", entity=request.organization,
                     request=request)
        messages.success(request, "Organization settings saved.")
        return redirect("workspace:settings")
    return render(request, "workspace/settings.html", {"form": form})


@login_required
def profile(request):
    return render(request, "workspace/profile.html")


def _valid_id(value):
    return ObjectId.is_valid(str(value))
