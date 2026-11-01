from django.shortcuts import redirect
from django.urls import reverse

from .models import Membership

SESSION_KEY = "camply_org_id"

# Paths a signed-in user can reach before belonging to an organization.
EXEMPT_PREFIXES = ("/accounts/", "/admin/", "/static/", "/workspace/onboarding", "/workspace/invite/")


class CurrentMembershipMiddleware:
    """Attach the user's active organization membership to the request.

    Sets request.membership and request.organization. Signed-in users with no
    membership are sent to onboarding to create or join an organization.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.membership = None
        request.organization = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            memberships = Membership.objects.filter(user=user).select_related("organization")
            selected = request.session.get(SESSION_KEY)
            membership = None
            if selected:
                membership = memberships.filter(organization_id=selected).first()
            if membership is None:
                membership = memberships.first()
            if membership is not None:
                request.membership = membership
                request.organization = membership.organization
                request.session[SESSION_KEY] = str(membership.organization_id)
            elif not request.path.startswith(EXEMPT_PREFIXES):
                return redirect(reverse("workspace:onboarding"))
        return self.get_response(request)
