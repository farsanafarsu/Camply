from django.core.cache import cache

from workspace.scoping import scope

from .models import ActionRequest, Alert

CACHE_SECONDS = 30


def cache_key(membership):
    return f"bell:{membership.organization_id}:{membership.user_id}"


def notifications(request):
    """Counts for the top-bar bell: unread open alerts and changes waiting for approval.

    Cached briefly per user and agency so every page doesn't pay for two count queries.
    """
    membership = getattr(request, "membership", None)
    if membership is None:
        return {}
    key = cache_key(membership)
    counts = cache.get(key)
    if counts is None:
        alerts = scope(Alert.objects.filter(resolved_at__isnull=True, is_read=False), membership, include_unassigned=True)
        pending = scope(ActionRequest.objects.filter(status=ActionRequest.Status.PENDING), membership)
        counts = {"unread_alerts": alerts.count(), "pending_approvals": pending.count()}
        cache.set(key, counts, CACHE_SECONDS)
    return counts


def forget_counts(request):
    """Call after changing alerts or approvals so the bell updates on the next page."""
    membership = getattr(request, "membership", None)
    if membership is not None:
        cache.delete(cache_key(membership))
