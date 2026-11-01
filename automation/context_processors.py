from workspace.scoping import scope

from .models import ActionRequest, Alert


def notifications(request):
    """Counts for the top-bar bell: unread open alerts and changes waiting for approval."""
    membership = getattr(request, "membership", None)
    if membership is None:
        return {}
    alerts = scope(Alert.objects.filter(resolved_at__isnull=True, is_read=False), membership, include_unassigned=True)
    pending = scope(ActionRequest.objects.filter(status=ActionRequest.Status.PENDING), membership)
    return {"unread_alerts": alerts.count(), "pending_approvals": pending.count()}
