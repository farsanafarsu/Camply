"""Page cost guards: query counts stay low, and cached numbers never outlive a change."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from ads.models import AdAccount, Campaign, CampaignStatus
from ads.services import sync_account
from billing.models import LedgerEntry
from workspace.models import Client, Membership, Organization, Role

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(settings):
    settings.CAMPLY_SANDBOX_ADAPTERS = True
    org = Organization.objects.create(name="Agency", state="Kerala")
    user = User.objects.create_user(email="owner@perf.test", password="perf-pass-123")
    Membership.objects.create(organization=org, user=user, role=Role.OWNER, all_clients=True)
    for n in range(5):
        client = Client.objects.create(organization=org, name=f"Client {n}", monthly_budget_paise=10_000_00)
        account = AdAccount.objects.create(organization=org, client=client, platform="meta",
                                           external_id=f"acc-{n}", name=f"Account {n}")
        Campaign.objects.create(organization=org, client=client, ad_account=account, platform="meta",
                                external_id=f"acc-{n}-c1", name=f"Campaign {n}", status=CampaignStatus.ACTIVE)
        sync_account(account, days=7)
        LedgerEntry.objects.create(organization=org, client=client, kind="deposit", amount_paise=50_000_00,
                                   entry_date="2026-11-01")
    return user


def queries_for(client, url):
    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx.captured_queries)


@pytest.mark.parametrize("url_name", ["billing:wallet", "ads:accounts"])
def test_list_pages_do_not_grow_with_clients(client, owner, url_name):
    """No per-client or per-account queries: 5 clients cost the same as 1."""
    client.force_login(owner)
    client.get(reverse(url_name))
    assert queries_for(client, reverse(url_name)) <= 8


def test_dashboard_is_cached_but_reflects_changes_immediately(client, owner):
    client.force_login(owner)
    home = reverse("dashboard:home")
    client.get(home)
    assert queries_for(client, home) <= 6  # served from cache

    campaign = Campaign.objects.get(name="Campaign 0")
    client.post(reverse("dashboard:campaign_status", args=[campaign.pk]), {"action": "pause"})
    response = client.get(home)
    statuses = {row["campaign"].name: row["campaign"].status for row in response.context["recent_campaigns"]}
    assert statuses.get("Campaign 0") == CampaignStatus.PAUSED


def test_wallet_balances_match_ledger(client, owner):
    client.force_login(owner)
    LedgerEntry.objects.create(organization=Organization.objects.get(), client=Client.objects.get(name="Client 0"),
                               kind="ad_spend", amount_paise=20_000_00, entry_date="2026-11-01")
    balances = {b["client"].name: b["balance_paise"] for b in client.get(reverse("billing:wallet")).context["balances"]}
    assert balances["Client 0"] == 30_000_00
    assert balances["Client 1"] == 50_000_00
