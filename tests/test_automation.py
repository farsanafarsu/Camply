"""Automation: rule evaluation, alert de-duplication, guarded changes and approvals."""

from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from ads.models import AdAccount, Campaign, CampaignStatus, MetricSnapshot
from automation.engine import run_rules
from automation.models import ActionRequest, Alert, Rule
from workspace.models import Client, Membership, Organization, Role

pytestmark = pytest.mark.django_db


def make_user(email):
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(email=email, password="auto-pass-123")
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


@pytest.fixture
def world(settings):
    settings.CAMPLY_SANDBOX_ADAPTERS = True
    org = Organization.objects.create(name="Agency", state="Kerala")
    client = Client.objects.create(organization=org, name="Alpha", monthly_budget_paise=100_000_00)
    account = AdAccount.objects.create(organization=org, client=client, platform="meta", external_id="acc-1",
                                       name="Alpha Meta")
    campaign = Campaign.objects.create(organization=org, client=client, ad_account=account, platform="meta",
                                       external_id="acc-1-c1", name="Lead gen", status=CampaignStatus.ACTIVE,
                                       daily_budget_paise=2_000_00)
    today = timezone.localdate()
    for offset in range(1, 4):  # ₹30,000 a day, 10 leads -> CPL ₹3,000
        MetricSnapshot.objects.create(organization=org, client=client, ad_account=account, campaign=campaign,
                                      platform="meta", date=today - timedelta(days=offset), spend_paise=30_000_00,
                                      impressions=50_000, clicks=900, leads=10)
    owner = make_user("owner@agency.test")
    Membership.objects.create(organization=org, user=owner, role=Role.OWNER, all_clients=True)
    manager = make_user("manager@agency.test")
    Membership.objects.create(organization=org, user=manager, role=Role.CAMPAIGN_MANAGER, all_clients=True)
    analyst = make_user("analyst@agency.test")
    Membership.objects.create(organization=org, user=analyst, role=Role.ANALYST, all_clients=True)
    return {"org": org, "client": client, "campaign": campaign, "owner": owner, "manager": manager,
            "analyst": analyst, "today": today}


def rule(world, kind, **params):
    return Rule.objects.create(organization=world["org"], name=kind, kind=kind, params=params,
                               recipients=["alerts@agency.test"])


def test_budget_rule_alerts_once_and_emails(world):
    rule(world, Rule.Kind.CLIENT_BUDGET, percent=80)
    # ₹90,000 today alone is 90% of the ₹1,00,000 monthly budget, whatever the date.
    c = world["campaign"]
    MetricSnapshot.objects.create(organization=world["org"], client=world["client"], ad_account=c.ad_account,
                                  campaign=c, platform="meta", date=world["today"], spend_paise=90_000_00)
    created = run_rules()
    assert len(created) == 1 and "monthly budget" in created[0].title
    assert len(mail.outbox) == 1
    assert run_rules() == []  # same problem, no duplicate alert


def test_campaign_daily_and_cpl_rules(world):
    rule(world, Rule.Kind.CAMPAIGN_DAILY, percent=100)
    rule(world, Rule.Kind.CPL_ABOVE, cpl_rupees=500, days=7)
    titles = [a.title for a in run_rules()]
    assert any("daily budget" in t for t in titles)
    assert any("cost per lead ₹3,000" in t for t in titles)


def test_no_delivery_rule(world):
    other = Campaign.objects.create(organization=world["org"], client=world["client"],
                                    ad_account=world["campaign"].ad_account, platform="meta", external_id="x",
                                    name="Silent", status=CampaignStatus.ACTIVE)
    rule(world, Rule.Kind.NO_DELIVERY, days=2)
    titles = [a.title for a in run_rules()]
    assert any(other.name in t for t in titles)
    assert not any("Lead gen" in t for t in titles)


def test_guarded_pause_needs_someone_else_to_approve(client, world):
    rule(world, Rule.Kind.GUARDED_PAUSE, cpl_rupees=500, days=7)
    run_rules()
    request = ActionRequest.objects.get()
    assert request.status == ActionRequest.Status.PENDING
    world["campaign"].refresh_from_db()
    assert world["campaign"].status == CampaignStatus.ACTIVE  # nothing applied yet

    client.force_login(world["analyst"])
    assert client.post(reverse("automation:approval_decide", args=[request.pk]),
                       {"decision": "approve"}).status_code == 403

    client.force_login(world["manager"])
    client.post(reverse("automation:approval_decide", args=[request.pk]), {"decision": "approve"})
    request.refresh_from_db()
    world["campaign"].refresh_from_db()
    assert request.status == ActionRequest.Status.APPLIED
    assert world["campaign"].status == CampaignStatus.PAUSED


def test_requester_cannot_approve_own_change(client, world):
    from automation.approvals import request_change

    change = request_change(world["campaign"], ActionRequest.Action.SET_DAILY_BUDGET, requested_by=world["manager"],
                            payload={"from_paise": 2_000_00, "to_paise": 5_000_00})
    client.force_login(world["manager"])
    client.post(reverse("automation:approval_decide", args=[change.pk]), {"decision": "approve"})
    change.refresh_from_db()
    assert change.status == ActionRequest.Status.PENDING
    client.force_login(world["owner"])
    client.post(reverse("automation:approval_decide", args=[change.pk]), {"decision": "approve"})
    world["campaign"].refresh_from_db()
    assert world["campaign"].daily_budget_paise == 5_000_00


def test_rule_form_and_bell(client, world):
    client.force_login(world["owner"])
    client.post(reverse("automation:rules"), {"name": "CPL watch", "kind": "cpl_above", "cpl_rupees": "500",
                                              "days": "7", "recipients": "me@agency.test"})
    assert Rule.objects.get(name="CPL watch").params["cpl_rupees"] == 500.0
    client.post(reverse("automation:run"))
    html = client.get(reverse("dashboard:home")).content.decode()
    assert 'class="bell-count"' in html
    alert = Alert.objects.first()
    client.post(reverse("automation:alert_action"), {"alert": str(alert.pk), "action": "resolve"})
    alert.refresh_from_db()
    assert alert.resolved_at is not None


def test_analyst_cannot_manage_rules(client, world):
    client.force_login(world["analyst"])
    assert client.get(reverse("automation:rules")).status_code == 403
    assert client.get(reverse("automation:alerts")).status_code == 200
