"""Platform admin console: superusers only, no agency needed."""

import pytest
from django.urls import reverse

from accounts.models import User
from workspace.models import Membership, Organization, Role

pytestmark = pytest.mark.django_db


def make_user(email, **extra):
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(email=email, password="console-pass-123", **extra)
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


@pytest.fixture
def people():
    org = Organization.objects.create(name="Agency A", state="Kerala")
    owner = make_user("owner@a.test")
    Membership.objects.create(organization=org, user=owner, role=Role.OWNER)
    admin = make_user("admin@camply.test", is_staff=True, is_superuser=True)
    return {"org": org, "owner": owner, "admin": admin}


def test_platform_admin_without_agency_sees_console(client, people):
    client.force_login(people["admin"])
    assert client.get(reverse("console:home")).status_code == 200
    assert client.get(reverse("console:agencies")).status_code == 200
    assert client.get(reverse("console:agency_detail", args=[people["org"].pk])).status_code == 200
    html = client.get(reverse("console:users")).content.decode()
    assert "owner@a.test" in html


def test_platform_admin_sees_every_agency_feature_as_owner(client, people):
    client.force_login(people["admin"])
    for name in ("dashboard:home", "dashboard:campaigns", "dashboard:reports", "billing:wallet",
                 "workspace:team", "workspace:settings", "dashboard:audit_log", "ads:accounts"):
        assert client.get(reverse(name)).status_code == 200, name
    html = client.get(reverse("dashboard:home")).content.decode()
    assert "Platform overview" in html and "Agency A" in html
    # Acting as Owner doesn't make them a listed member of the agency.
    assert not Membership.objects.filter(user=people["admin"]).exists()


def test_platform_admin_can_switch_to_any_agency(client, people):
    other = Organization.objects.create(name="Agency B", state="Kerala")
    client.force_login(people["admin"])
    client.post(reverse("workspace:switch"), {"organization": str(other.pk)})
    response = client.get(reverse("dashboard:home"))
    assert response.context["current_org"] == other


def test_agency_member_cannot_switch_to_other_agency(client, people):
    other = Organization.objects.create(name="Agency B", state="Kerala")
    client.force_login(people["owner"])
    assert client.post(reverse("workspace:switch"), {"organization": str(other.pk)}).status_code == 403


def test_sign_in_lands_platform_admin_on_dashboard(client, people):
    response = client.post(reverse("account_login"),
                           {"login": "admin@camply.test", "password": "console-pass-123"})
    assert response.url == reverse("dashboard:home")
    assert client.get(response.url).status_code == 200


def test_platform_admin_with_no_agencies_goes_to_console(client):
    admin = make_user("solo@camply.test", is_staff=True, is_superuser=True)
    client.force_login(admin)
    response = client.get(reverse("dashboard:home"))
    assert response.status_code == 302 and response.url == reverse("console:home")
    assert client.get(reverse("console:home")).status_code == 200


def test_agency_owner_cannot_open_console(client, people):
    client.force_login(people["owner"])
    for name in ("console:home", "console:agencies", "console:users"):
        assert client.get(reverse(name)).status_code == 403


def test_disable_and_enable_user(client, people):
    client.force_login(people["admin"])
    owner = people["owner"]
    client.post(reverse("console:user_status", args=[owner.pk]), {"action": "disable"})
    owner.refresh_from_db()
    assert owner.is_active is False
    client.post(reverse("console:user_status", args=[owner.pk]), {"action": "enable"})
    owner.refresh_from_db()
    assert owner.is_active is True


def test_admin_cannot_disable_self(client, people):
    client.force_login(people["admin"])
    client.post(reverse("console:user_status", args=[people["admin"].pk]), {"action": "disable"})
    people["admin"].refresh_from_db()
    assert people["admin"].is_active is True


def test_add_normal_user_to_agency_can_sign_in(client, people):
    client.force_login(people["admin"])
    response = client.post(reverse("console:user_add"), {
        "email": "New.User@Agency.test", "first_name": "New", "password": "Test-Pass-2026",
        "organization": str(people["org"].pk), "role": Role.OWNER,
    })
    assert response.status_code == 302
    user = User.objects.get(email="new.user@agency.test")
    assert not user.is_superuser and not user.is_staff
    membership = Membership.objects.get(user=user, organization=people["org"])
    assert membership.role == Role.OWNER and membership.all_clients

    client.logout()
    response = client.post(reverse("account_login"), {"login": "new.user@agency.test", "password": "Test-Pass-2026"})
    assert response.url == reverse("dashboard:home")
    assert client.get(reverse("console:home")).status_code == 403


def test_add_user_turns_existing_platform_admin_into_normal_user(client, people):
    other_admin = User.objects.create_user(email="new.user@agency.test", password="x" * 10,
                                           is_staff=True, is_superuser=True)
    client.force_login(people["admin"])
    client.post(reverse("console:user_add"), {
        "email": "new.user@agency.test", "password": "Test-Pass-2026",
        "organization": str(people["org"].pk), "role": Role.OWNER,
    })
    other_admin.refresh_from_db()
    assert not other_admin.is_superuser
    assert other_admin.check_password("Test-Pass-2026")


def test_cannot_remove_own_platform_admin(client, people):
    client.force_login(people["admin"])
    response = client.post(reverse("console:user_add"), {
        "email": "admin@camply.test", "password": "whatever-123",
        "organization": str(people["org"].pk), "role": Role.OWNER,
    })
    assert response.status_code == 200
    people["admin"].refresh_from_db()
    assert people["admin"].is_superuser


def test_agency_owner_cannot_add_users_through_console(client, people):
    client.force_login(people["owner"])
    response = client.post(reverse("console:user_add"), {
        "email": "x@y.test", "password": "whatever-123", "platform_admin": "on",
    })
    assert response.status_code == 403
    assert not User.objects.filter(email="x@y.test").exists()


def test_admin_with_no_agencies_adds_one_and_gets_every_feature(client):
    admin = make_user("fresh@camply.test", is_staff=True, is_superuser=True)
    client.force_login(admin)
    html = client.get(reverse("console:home")).content.decode()
    assert "Start by adding an agency" in html

    response = client.post(reverse("console:agency_add"),
                           {"name": "Test Media", "state": "Kerala", "city": "Thiruvananthapuram"})
    assert response.status_code == 302 and response.url == reverse("dashboard:home")
    org = Organization.objects.get(name="Test Media")

    response = client.get(reverse("dashboard:home"))
    assert response.status_code == 200 and response.context["current_org"] == org
    html = response.content.decode()
    for feature in ("Campaigns", "Reports", "Wallet &amp; Billing", "Team", "Platform overview"):
        assert feature in html, feature


def test_agency_owner_cannot_add_agencies_through_console(client, people):
    client.force_login(people["owner"])
    response = client.post(reverse("console:agency_add"), {"name": "Sneaky", "state": "Kerala"})
    assert response.status_code == 403
    assert not Organization.objects.filter(name="Sneaky").exists()
