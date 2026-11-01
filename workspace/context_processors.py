from .models import Membership


def workspace(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {
        "current_membership": getattr(request, "membership", None),
        "current_org": getattr(request, "organization", None),
        "user_memberships": Membership.objects.filter(user=user).select_related("organization"),
    }
