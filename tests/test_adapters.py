from datetime import date
from types import SimpleNamespace

import pytest

from ads.adapters.base import Capability, NotConfigured, UnsupportedAction
from ads.adapters.meta import MetaAdapter
from ads.adapters.pending import GoogleAdsAdapter
from ads.adapters.sandbox import SandboxAdapter
from ads.models import CampaignStatus

ACCOUNT = SimpleNamespace(external_id="meta-1001", name="Test account")


def test_sandbox_is_deterministic():
    a = SandboxAdapter(platform="meta").fetch_daily_metrics(ACCOUNT, date(2026, 10, 1), date(2026, 10, 7))
    b = SandboxAdapter(platform="meta").fetch_daily_metrics(ACCOUNT, date(2026, 10, 1), date(2026, 10, 7))
    assert a == b
    assert a and all(r.spend_paise > 0 and r.clicks <= r.impressions for r in a)


def test_sandbox_uses_given_campaign_names():
    adapter = SandboxAdapter(platform="google", campaign_names=["Search · Brand"])
    [campaign] = adapter.list_campaigns(ACCOUNT)
    assert campaign.name == "Search · Brand"
    assert campaign.external_id == "meta-1001-c1"
    assert campaign.status in (CampaignStatus.ACTIVE, CampaignStatus.PAUSED)


def test_pending_connector_reports_not_configured():
    adapter = GoogleAdsAdapter()
    assert not adapter.supports(Capability.PAUSE)
    with pytest.raises(NotConfigured):
        adapter.list_campaigns(ACCOUNT)
    with pytest.raises(UnsupportedAction):
        adapter.pause_campaign(SimpleNamespace(external_id="1"))


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.content = b"x"

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, url, params=None, timeout=None):
        self.calls.append((method, url, params))
        return FakeResponse(self.payload)


def test_meta_insights_are_mapped_to_paise_and_leads(settings):
    settings.META_GRAPH_API_VERSION = "v23.0"
    connection = SimpleNamespace(access_token="token")
    session = FakeSession({"data": [{
        "campaign_id": "123", "date_start": "2026-10-01", "spend": "1234.56", "impressions": "10000",
        "clicks": "250", "reach": "8000",
        "actions": [{"action_type": "lead", "value": "12"}, {"action_type": "link_click", "value": "240"}],
    }]})
    [row] = MetaAdapter(connection, session=session).fetch_daily_metrics(
        SimpleNamespace(external_id="999"), date(2026, 10, 1), date(2026, 10, 1)
    )
    assert row.spend_paise == 123456
    assert row.leads == 12
    assert row.revenue_paise is None
    method, url, params = session.calls[0]
    assert url.endswith("/v23.0/act_999/insights")
    assert params["access_token"] == "token"
