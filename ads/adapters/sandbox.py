"""Deterministic demo data for development, demos and accounts without a live connection.

Every number is derived from a hash of the account, campaign and date, so a re-sync
produces the same results and tests are stable.
"""

import hashlib
from datetime import date, timedelta

from ..models import CampaignStatus, Platform
from .base import AdPlatformAdapter, Capability, RemoteAccount, RemoteCampaign, RemoteMetricRow

# Per platform: (relative daily spend in rupees, CTR %, CPC in rupees, lead rate % of clicks, ROAS or None)
PROFILES = {
    Platform.META: (6800, 1.6, 9.5, 11.0, 4.6),
    Platform.GOOGLE: (4500, 3.8, 22.0, 9.0, 5.1),
    Platform.TIKTOK: (2900, 1.1, 6.5, 5.0, None),
    Platform.OPENAI: (1950, 2.4, 18.0, 7.5, None),
}

OBJECTIVES = {
    Platform.META: "Leads",
    Platform.GOOGLE: "Search leads",
    Platform.TIKTOK: "Reach",
    Platform.OPENAI: "Traffic",
}


def _unit(*parts) -> float:
    """A stable pseudo-random number in [0, 1) from the given parts."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class SandboxAdapter(AdPlatformAdapter):
    capabilities = frozenset(
        {Capability.READ_CAMPAIGNS, Capability.READ_METRICS, Capability.PAUSE, Capability.RESUME,
         Capability.UPDATE_BUDGET}
    )

    def __init__(self, connection=None, *, platform=Platform.META, campaign_names=None):
        super().__init__(connection)
        self.platform = platform
        self.campaign_names = campaign_names

    def list_accounts(self):
        return [RemoteAccount(external_id=f"sandbox-{self.platform}", name=f"Sandbox {self.platform}")]

    def _names(self, account):
        if self.campaign_names:
            return self.campaign_names
        return [f"{account.name} · Campaign {n}" for n in range(1, 4)]

    def list_campaigns(self, account):
        daily, *_ = PROFILES[self.platform]
        campaigns = []
        for index, name in enumerate(self._names(account)):
            external_id = f"{account.external_id}-c{index + 1}"
            roll = _unit(external_id, "status")
            status = CampaignStatus.ACTIVE if roll < 0.75 else CampaignStatus.PAUSED
            budget_rupees = round(daily * (0.5 + _unit(external_id, "budget")) / 100) * 100
            campaigns.append(
                RemoteCampaign(
                    external_id=external_id,
                    name=name,
                    status=status,
                    objective=OBJECTIVES[self.platform],
                    daily_budget_paise=budget_rupees * 100,
                    start_date=date.today() - timedelta(days=60 + int(30 * _unit(external_id, "start"))),
                )
            )
        return campaigns

    def fetch_daily_metrics(self, account, start, end):
        daily, ctr, cpc, lead_rate, roas = PROFILES[self.platform]
        rows = []
        for campaign in self.list_campaigns(account):
            weight = 0.6 + _unit(campaign.external_id, "weight")
            day = start
            while day <= end:
                # Gentle upward trend with weekly rhythm and daily noise.
                age = (day - (end - timedelta(days=60))).days
                trend = 0.8 + 0.4 * max(0, min(age, 60)) / 60
                weekly = 1.0 + 0.12 * ((day.weekday() in (5, 6)) - 0.3)
                noise = 0.8 + 0.4 * _unit(campaign.external_id, day, "noise")
                if campaign.status == CampaignStatus.PAUSED and day > end - timedelta(days=7):
                    day += timedelta(days=1)
                    continue
                spend_rupees = daily * weight * trend * weekly * noise / 3
                clicks = max(1, int(spend_rupees / (cpc * (0.85 + 0.3 * _unit(campaign.external_id, day, "cpc")))))
                impressions = int(clicks / (ctr / 100))
                leads = int(clicks * lead_rate / 100 * (0.8 + 0.4 * _unit(campaign.external_id, day, "leads")))
                spend_paise = int(spend_rupees * 100)
                rows.append(
                    RemoteMetricRow(
                        campaign_external_id=campaign.external_id,
                        date=day,
                        spend_paise=spend_paise,
                        impressions=impressions,
                        clicks=clicks,
                        reach=int(impressions * 0.62),
                        leads=leads,
                        conversions=leads,
                        revenue_paise=int(spend_paise * roas * (0.85 + 0.3 * _unit(campaign.external_id, day)))
                        if roas
                        else None,
                    )
                )
                day += timedelta(days=1)
        return rows

    def pause_campaign(self, campaign):
        self.require(Capability.PAUSE)

    def resume_campaign(self, campaign):
        self.require(Capability.RESUME)

    def update_daily_budget(self, campaign, daily_budget_paise):
        self.require(Capability.UPDATE_BUDGET)
