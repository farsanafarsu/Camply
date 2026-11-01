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


def test_platform_admin_is_not_sent_to_onboarding(client, people):
    client.force_login(people["admin"])
    response = client.get(reverse("dashboard:campaigns"))
    assert response.status_code == 302 and response.url == reverse("console:home")


def test_sign_in_lands_platform_admin_in_console(client, people):
    response = client.post(reverse("account_login"),
                           {"login": "admin@camply.test", "password": "console-pass-123"})
    assert response.url == reverse("console:home")


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
