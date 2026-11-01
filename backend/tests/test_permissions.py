from types import SimpleNamespace

import pytest

from workspace.models import Role
from workspace.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS, has_perm, permission_matrix


def member(role):
    return SimpleNamespace(role=role)


def test_every_role_has_a_permission_set():
    assert set(ROLE_PERMISSIONS) == set(Role)
    for perms in ROLE_PERMISSIONS.values():
        assert perms <= ALL_PERMISSIONS


def test_owner_can_do_everything():
    assert all(has_perm(member(Role.OWNER), p) for p in ALL_PERMISSIONS)


@pytest.mark.parametrize("role", [Role.ANALYST, Role.FINANCE, Role.CLIENT, Role.VIEWER])
def test_read_only_roles_cannot_change_campaigns(role):
    assert not has_perm(member(role), "campaigns.edit")


def test_admin_cannot_manage_billing_or_org():
    admin = member(Role.ADMIN)
    assert has_perm(admin, "team.manage")
    assert not has_perm(admin, "billing.manage")
    assert not has_perm(admin, "org.manage")


def test_client_can_approve_but_not_see_wallet():
    client = member(Role.CLIENT)
    assert has_perm(client, "creatives.approve")
    assert not has_perm(client, "budget.view")


def test_no_membership_has_no_permissions():
    assert not has_perm(None, "dashboard.view")


def test_unknown_permission_is_a_bug():
    with pytest.raises(ValueError):
        has_perm(member(Role.OWNER), "campaigns.delete_everything")


def test_matrix_shape():
    roles, rows = permission_matrix()
    assert len(roles) == len(Role)
    assert all(len(allowed) == len(roles) for _, _, allowed in rows)
