from bson import ObjectId
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit import log as audit
from workspace.decorators import require_perm
from workspace.permissions import has_perm
from workspace.scoping import allowed_clients, ensure_client_allowed, get_scoped_or_404, scope

from .approvals import ApprovalError, decide
from .context_processors import forget_counts
from .engine import run_rules
from .forms import RuleForm
from .models import ActionRequest, Alert, Rule


@login_required
@require_perm("automation.manage")
def rules(request):
    membership = request.membership
    form = RuleForm(request.POST or None, clients=allowed_clients(membership),
                    initial={"recipients": request.user.email})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if data["client"] is not None:
            ensure_client_allowed(membership, data["client"])
        if data["client"] is None and not membership.sees_all_clients:
            form.add_error("client", "Choose one of your clients.")
        else:
            rule = Rule.objects.create(
                organization=request.organization, client=data["client"], name=data["name"], kind=data["kind"],
                params=data["params"], recipients=data["recipients"], notify_email=bool(data["recipients"]),
                created_by=request.user)
            audit.record(organization=request.organization, action="rule.create", entity=rule, request=request,
                         after={"kind": rule.kind, "params": rule.params})
            messages.success(request, f"Rule “{rule.name}” is on. Camply checks it every hour.")
            return redirect("automation:rules")
    return render(request, "automation/rules.html", {
        "rules": scope(Rule.objects.select_related("client"), membership, include_unassigned=membership.sees_all_clients),
        "form": form, "params": {k.value: v for k, v in Rule.PARAMS.items()},
    })


@login_required
@require_POST
@require_perm("automation.manage")
def rule_action(request, pk):
    membership = request.membership
    if not ObjectId.is_valid(pk):
        raise Http404
    # Rules for "all clients" are only visible to people who see all clients.
    rule = scope(Rule.objects.all(), membership, include_unassigned=membership.sees_all_clients).filter(pk=pk).first()
    if rule is None:
        raise Http404
    action = request.POST.get("action")
    if action == "toggle":
        rule.is_active = not rule.is_active
        rule.save(update_fields=["is_active"])
        messages.success(request, f"“{rule.name}” is now {'on' if rule.is_active else 'off'}.")
    elif action == "delete":
        audit.record(organization=request.organization, action="rule.delete", entity=rule, request=request)
        rule.delete()
        messages.success(request, "Rule deleted.")
    return redirect("automation:rules")


@login_required
@require_POST
@require_perm("automation.manage")
def run_now(request):
    created = run_rules(organization_id=request.organization.pk)
    forget_counts(request)
    messages.success(request, f"Checked every rule. {len(created)} new alert{'s' if len(created) != 1 else ''}.")
    return redirect("automation:alerts")


@login_required
@require_perm("dashboard.view")
def alerts(request):
    membership = request.membership
    show = request.GET.get("show", "open")
    qs = scope(Alert.objects.select_related("client"), membership, include_unassigned=True)
    qs = qs.filter(resolved_at__isnull=show != "resolved")
    return render(request, "automation/alerts.html", {"alerts": qs[:200], "show": show})


@login_required
@require_POST
@require_perm("dashboard.view")
def alert_action(request):
    membership = request.membership
    qs = scope(Alert.objects.filter(resolved_at__isnull=True), membership, include_unassigned=True)
    alert_id = request.POST.get("alert", "")
    forget_counts(request)
    if request.POST.get("action") == "read_all":
        qs.update(is_read=True)
    elif ObjectId.is_valid(alert_id):
        alert = qs.filter(pk=alert_id).first()
        if alert is None:
            raise Http404
        alert.resolved_at = timezone.now()
        alert.is_read = True
        alert.save(update_fields=["resolved_at", "is_read"])
        messages.success(request, "Alert resolved.")
    return redirect(request.POST.get("next") if request.POST.get("next", "").startswith("/automation/") else "automation:alerts")


@login_required
@require_perm("campaigns.view")
def approvals(request):
    membership = request.membership
    qs = scope(ActionRequest.objects.select_related("campaign", "client", "requested_by", "decided_by"), membership)
    return render(request, "automation/approvals.html", {
        "pending": qs.filter(status=ActionRequest.Status.PENDING),
        "history": qs.exclude(status=ActionRequest.Status.PENDING)[:50],
        "can_decide": has_perm(membership, "campaigns.edit"),
    })


@login_required
@require_POST
@require_perm("campaigns.edit")
def approval_decide(request, pk):
    action_request = get_scoped_or_404(ActionRequest.objects.select_related("campaign"), request.membership, pk=pk)
    approve = request.POST.get("decision") == "approve"
    forget_counts(request)
    try:
        decide(action_request, approve=approve, user=request.user, request=request)
    except ApprovalError as exc:
        messages.error(request, str(exc))
        return redirect("automation:approvals")
    audit.record(organization=request.organization, action="approval.decide", entity=action_request.campaign,
                 request=request, after={"action": action_request.action, "status": action_request.status},
                 message=action_request.result_message)
    if action_request.status == ActionRequest.Status.FAILED:
        messages.error(request, f"Approved, but the platform refused: {action_request.result_message}")
    else:
        messages.success(request, f"{action_request.get_status_display()}: {action_request.description} "
                                  f"for {action_request.campaign.name}.")
    return redirect("automation:approvals")
