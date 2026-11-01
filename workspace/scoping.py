"""Tenant scoping. Every query for tenant data must go through `scope()`.

Data belongs to an organization and (usually) to one of its clients. A membership can see
its organization's data, limited to the clients it is assigned unless it sees all clients.
"""

from django.core.exceptions import PermissionDenied

from .models import Client


def allowed_clients(membership):
    if membership is None:
        return Client.objects.none()
    qs = Client.objects.filter(organization_id=membership.organization_id)
    if membership.sees_all_clients:
        return qs
    return qs.filter(pk__in=list(membership.clients.values_list("pk", flat=True)))


def allowed_client_ids(membership):
    # Pages call this several times per request; remember the answer on the membership.
    cached = getattr(membership, "_allowed_client_ids", None)
    if cached is None:
        cached = list(allowed_clients(membership).values_list("pk", flat=True))
        if membership is not None:
            membership._allowed_client_ids = cached
    return cached


def scope(queryset, membership, *, client_field="client", include_unassigned=None):
    """Limit a queryset to the membership's organization and allowed clients.

    Records with no client (e.g. an ad account not yet assigned) are visible only to
    memberships that see all clients, unless include_unassigned says otherwise.
    """
    if membership is None:
        return queryset.none()
    queryset = queryset.filter(organization_id=membership.organization_id)
    if client_field is None or membership.sees_all_clients:
        return queryset
    ids = allowed_client_ids(membership)
    if include_unassigned:
        from django.db.models import Q

        return queryset.filter(Q(**{f"{client_field}__in": ids}) | Q(**{f"{client_field}__isnull": True}))
    return queryset.filter(**{f"{client_field}__in": ids})


def get_scoped_or_404(queryset, membership, *, client_field="client", **lookup):
    from bson import ObjectId
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    if "pk" in lookup and not ObjectId.is_valid(str(lookup["pk"])):
        raise Http404
    return get_object_or_404(scope(queryset, membership, client_field=client_field), **lookup)


def ensure_client_allowed(membership, client):
    if client is None:
        if not membership.sees_all_clients:
            raise PermissionDenied
        return
    if client.organization_id != membership.organization_id:
        raise PermissionDenied
    if not membership.sees_all_clients and client.pk not in allowed_client_ids(membership):
        raise PermissionDenied
