"""Tenant isolation and role enforcement, end to end through views (needs MongoDB running)."""

import pytest
from django.urls import reverse

from accounts.models import User
from ads.models import AdAccount, Campaign, CampaignStatus, MetricSnapshot
from ads.services import sync_account
from workspace.models import Client, Membership, Organization, Role

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-123"


def make_user(email):
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(email=email, password=PASSWORD)
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


@pytest.fixture
def world():
    org = Organization.objects.create(name="Agency A", state="Kerala")
    other_org = Organization.objects.create(name="Agency B", state="Kerala")
    alpha = Client.objects.create(organization=org, name="Alpha")
    beta = Client.objects.create(organization=org, name="Beta")
    outsider = Client.objects.create(organization=other_org, name="Outsider")

    campaigns = {}
    for client, ext in ((alpha, "a"), (beta, "b"), (outsider, "x")):
        account = AdAccount.objects.create(
            organization=client.organization, client=client, platform="meta", external_id=f"acc-{ext}",
            name=f"{client.name} Meta",
        )
        Campaign.objects.create(
            organization=client.organization, client=client, ad_account=account, platform="meta",
            external_id=f"acc-{ext}-c1", name=f"{client.name} campaign",
        )
        sync_account(account, days=7)
        campaigns[client.name] = Campaign.objects.get(ad_account=account)

    owner = make_user("owner@a.test")
    Membership.objects.create(organization=org, user=owner, role=Role.OWNER)
    analyst = make_user("analyst@a.test")
    m = Membership.objects.create(organization=org, user=analyst, role=Role.ANALYST)
    m.clients.set([alpha])
    manager = make_user("manager@a.test")
    m = Membership.objects.create(organization=org, user=manager, role=Role.CAMPAIGN_MANAGER)
    m.clients.set([beta])
    return {"org": org, "campaigns": campaigns, "owner": owner, "analyst": analyst, "manager": manager}


def login(client, user):
    client.force_login(user)


def test_sync_writes_metrics(world):
    assert MetricSnapshot.objects.filter(campaign=world["campaigns"]["Alpha"]).count() == 7


def test_owner_sees_all_own_clients_but_not_other_orgs(client, world):
    login(client, world["owner"])
    html = client.get(reverse("dashboard:campaigns")).content.decode()
    assert "Alpha campaign" in html and "Beta campaign" in html
    assert "Outsider campaign" not in html
    other = world["campaigns"]["Outsider"]
    assert client.get(reverse("dashboard:campaign_detail", args=[other.pk])).status_code == 404


def test_analyst_limited_to_assigned_clients(client, world):
    login(client, world["analyst"])
    html = client.get(reverse("dashboard:campaigns")).content.decode()
    assert "Alpha campaign" in html
    assert "Beta campaign" not in html
    beta = world["campaigns"]["Beta"]
    assert client.get(reverse("dashboard:campaign_detail", args=[beta.pk])).status_code == 404


def test_analyst_cannot_pause_even_by_direct_post(client, world):
    login(client, world["analyst"])
    alpha = world["campaigns"]["Alpha"]
    response = client.post(reverse("dashboard:campaign_status", args=[alpha.pk]), {"action": "pause"})
    assert response.status_code == 403
    alpha.refresh_from_db()
    assert alpha.status != CampaignStatus.PAUSED


def test_manager_can_pause_assigned_campaign_only(client, world):
    login(client, world["manager"])
    beta = world["campaigns"]["Beta"]
    beta.status = CampaignStatus.ACTIVE
    beta.save()
    client.post(reverse("dashboard:campaign_status", args=[beta.pk]), {"action": "pause"})
    beta.refresh_from_db()
    assert beta.status == CampaignStatus.PAUSED

    alpha = world["campaigns"]["Alpha"]
    response = client.post(reverse("dashboard:campaign_status", args=[alpha.pk]), {"action": "pause"})
    assert response.status_code == 404


@pytest.mark.parametrize("url_name", ["billing:wallet", "workspace:settings", "dashboard:audit_log"])
def test_analyst_blocked_from_finance_and_admin_pages(client, world, url_name):
    login(client, world["analyst"])
    assert client.get(reverse(url_name)).status_code == 403


def test_dashboard_totals_respect_scope(client, world):
    login(client, world["analyst"])
    response = client.get(reverse("dashboard:home"))
    alpha_spend = sum(MetricSnapshot.objects.filter(campaign=world["campaigns"]["Alpha"])
                      .values_list("spend_paise", flat=True))
    assert response.context["kpis"]["spend_paise"] == alpha_spend


def test_visitors_see_home_page_and_members_see_dashboard(client, world):
    response = client.get("/")
    assert response.status_code == 200
    assert "landing.html" in [t.name for t in response.templates]
    assert "Alpha campaign" not in response.content.decode()

    login(client, world["owner"])
    response = client.get("/")
    assert "dashboard/home.html" in [t.name for t in response.templates]


def test_user_without_membership_goes_to_onboarding(client, world):
    loner = make_user("new@x.test")
    login(client, loner)
    response = client.get(reverse("dashboard:home"))
    assert response.status_code == 302
    assert response.url == reverse("workspace:onboarding")


def test_password_reset_link_works_with_mongodb_ids(client, world, mailoutbox):
    import re

    response = client.post(reverse("account_reset_password"), {"email": "owner@a.test"})
    assert response.status_code == 302
    link = re.search(r"/accounts/password/reset/key/\S+", mailoutbox[0].body).group(0)
    response = client.get(link, follow=True)
    form_url = response.redirect_chain[-1][0]
    client.post(form_url, {"password1": "Brand-New-Pass-2026", "password2": "Brand-New-Pass-2026"})
    world["owner"].refresh_from_db()
    assert world["owner"].check_password("Brand-New-Pass-2026")


def test_stale_sign_in_form_reloads_with_a_note():
    from django.test import Client

    browser = Client(enforce_csrf_checks=True)
    browser.get(reverse("account_login"))
    response = browser.post(reverse("account_login"),
                            {"csrfmiddlewaretoken": "stale" * 8, "login": "a@b.test", "password": "x"})
    assert response.status_code == 302 and response.url == reverse("account_login")
    page = browser.get(response.url).content.decode()
    assert "That page had expired" in page


def test_stale_form_elsewhere_shows_friendly_page(world):
    from django.test import Client

    browser = Client(enforce_csrf_checks=True)
    browser.force_login(world["owner"])
    response = browser.post(reverse("workspace:switch"), {"organization": "x"})
    assert response.status_code == 403
    assert "This page expired" in response.content.decode()
