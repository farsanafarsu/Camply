from bson import ObjectId
from django.shortcuts import redirect
from django.urls import reverse

from .models import Membership, Organization, Role

SESSION_KEY = "camply_org_id"

# Paths a signed-in user can reach before belonging to an organization.
EXEMPT_PREFIXES = (
    "/accounts/", "/admin/", "/static/", "/platform/", "/workspace/onboarding", "/workspace/invite/",
)


def platform_admin_memberships(user):
    """One unsaved Owner membership per organization: what a platform admin can act as."""
    return [
        Membership(organization=org, user=user, role=Role.OWNER, all_clients=True)
        for org in Organization.objects.order_by("name")
    ]


class CurrentMembershipMiddleware:
    """Attach the user's active organization membership to the request.

    Sets request.membership and request.organization. Signed-in users with no
    membership are sent to onboarding to create or join an organization.

    Platform admins (superusers) can open any organization with Owner access. Their
    membership there is an unsaved Owner membership, so it never appears in the
    agency's member list and grants nothing once they stop being a platform admin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.membership = None
        request.organization = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            selected = request.session.get(SESSION_KEY)
            if user.is_superuser:
                membership = self._platform_admin_membership(user, selected)
            else:
                # One query; the agency switcher reuses this list (see context_processors).
                memberships = list(Membership.objects.filter(user=user).select_related("organization"))
                request.user_memberships = memberships
                membership = next((m for m in memberships if str(m.organization_id) == selected), None) \
                    or (memberships[0] if memberships else None)
            if membership is not None:
                request.membership = membership
                request.organization = membership.organization
                if selected != str(membership.organization_id):
                    request.session[SESSION_KEY] = str(membership.organization_id)
            elif not request.path.startswith(EXEMPT_PREFIXES):
                # A platform admin with no agencies on Camply yet only has the console.
                if user.is_superuser:
                    return redirect(reverse("console:home"))
                return redirect(reverse("workspace:onboarding"))
        return self.get_response(request)

    @staticmethod
    def _platform_admin_membership(user, selected):
        org = None
        if selected and ObjectId.is_valid(selected):
            org = Organization.objects.filter(pk=selected).first()
        if org is None:
            own = Membership.objects.filter(user=user).select_related("organization").first()
            org = own.organization if own else Organization.objects.order_by("name").first()
        if org is None:
            return None
        return Membership(organization=org, user=user, role=Role.OWNER, all_clients=True)
