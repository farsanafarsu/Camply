"""Deciding on guarded changes: nothing here runs until a person with the right role approves it."""

from django.utils import timezone

from ads.adapters import AdapterError
from ads.models import CampaignStatus
from ads.services import set_campaign_status, set_daily_budget

from .models import ActionRequest


class ApprovalError(Exception):
    pass


def request_change(campaign, action, *, requested_by=None, source=ActionRequest.Source.USER, reason="", payload=None):
    if ActionRequest.objects.filter(campaign=campaign, action=action, status=ActionRequest.Status.PENDING).exists():
        raise ApprovalError("The same change is already waiting for approval.")
    return ActionRequest.objects.create(
        organization_id=campaign.organization_id, client_id=campaign.client_id, campaign=campaign, action=action,
        payload=payload or {}, reason=reason, source=source, requested_by=requested_by,
    )


def decide(action_request, *, approve, user, request=None):
    """Approve (and apply) or reject a pending change."""
    if action_request.status != ActionRequest.Status.PENDING:
        raise ApprovalError("This request has already been decided.")
    if action_request.requested_by_id and action_request.requested_by_id == user.pk:
        raise ApprovalError("Someone else has to approve a change you asked for.")
    action_request.decided_by = user
    action_request.decided_at = timezone.now()
    if not approve:
        action_request.status = ActionRequest.Status.REJECTED
        action_request.save()
        return action_request
    campaign = action_request.campaign
    try:
        if action_request.action == ActionRequest.Action.PAUSE:
            set_campaign_status(campaign, CampaignStatus.PAUSED, actor=user, request=request)
        elif action_request.action == ActionRequest.Action.RESUME:
            set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=user, request=request)
        elif action_request.action == ActionRequest.Action.SET_DAILY_BUDGET:
            set_daily_budget(campaign, int(action_request.payload["to_paise"]), actor=user, request=request)
        action_request.status = ActionRequest.Status.APPLIED
        action_request.result_message = "Applied on the platform."
    except (AdapterError, ValueError) as exc:
        action_request.status = ActionRequest.Status.FAILED
        action_request.result_message = str(exc)[:300]
    action_request.save()
    return action_request
