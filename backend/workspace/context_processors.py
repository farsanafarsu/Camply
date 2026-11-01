from .middleware import platform_admin_memberships
from .models import Membership


def workspace(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    if user.is_superuser:
        memberships = platform_admin_memberships(user)
    else:
        # Already loaded by CurrentMembershipMiddleware for this request.
        memberships = getattr(request, "user_memberships", None)
        if memberships is None:
            memberships = Membership.objects.filter(user=user).select_related("organization")
    return {
        "current_membership": getattr(request, "membership", None),
        "current_org": getattr(request, "organization", None),
        "user_memberships": memberships,
    }
