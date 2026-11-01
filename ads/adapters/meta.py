"""Meta (Facebook and Instagram) Marketing API adapter.

Read access: ad accounts, campaigns and daily campaign insights; plus pause/resume.
Requires a Meta app with ads_read / ads_management approved, and a user access token
obtained through Meta's OAuth flow. Verify field names against the Graph API version in
settings.META_GRAPH_API_VERSION before going live.
"""

from datetime import date, datetime

import requests
from django.conf import settings

from camply.money import rupees_to_paise

from ..models import CampaignStatus, Platform
from .base import (
    AdapterError,
    AdPlatformAdapter,
    AuthExpired,
    Capability,
    NotConfigured,
    RemoteAccount,
    RemoteCampaign,
    RemoteMetricRow,
)

GRAPH = "https://graph.facebook.com"
LEAD_ACTION_TYPES = {"lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"}
PURCHASE_ACTION_TYPES = {"purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"}

STATUS_MAP = {
    "ACTIVE": CampaignStatus.ACTIVE,
    "PAUSED": CampaignStatus.PAUSED,
    "ARCHIVED": CampaignStatus.ARCHIVED,
    "DELETED": CampaignStatus.ARCHIVED,
    "IN_PROCESS": CampaignStatus.PENDING_APPROVAL,
    "WITH_ISSUES": CampaignStatus.ERROR,
}


def _minor_units_to_paise(value) -> int | None:
    # Meta reports budgets in the account currency's minor unit (paise for INR).
    return int(value) if value not in (None, "") else None


def _parse_date(value) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


class MetaAdapter(AdPlatformAdapter):
    platform = Platform.META
    capabilities = frozenset(
        {Capability.READ_CAMPAIGNS, Capability.READ_METRICS, Capability.PAUSE, Capability.RESUME}
    )
    docs_url = "https://developers.facebook.com/docs/marketing-apis/"

    def __init__(self, connection=None, session=None):
        super().__init__(connection)
        self.session = session or requests.Session()

    @property
    def base_url(self):
        return f"{GRAPH}/{settings.META_GRAPH_API_VERSION}"

    def _token(self):
        token = self.connection.access_token if self.connection else ""
        if not token:
            raise NotConfigured("This Meta connection has no access token. Reconnect the account.")
        return token

    def _request(self, method, path, **params):
        params["access_token"] = self._token()
        try:
            response = self.session.request(method, f"{self.base_url}/{path}", params=params, timeout=30)
        except requests.RequestException as exc:
            raise AdapterError(f"Could not reach Meta: {exc}") from exc
        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            error = payload.get("error", {})
            if error.get("code") == 190:
                raise AuthExpired(error.get("message", "Meta access token expired."))
            raise AdapterError(error.get("message", f"Meta API error {response.status_code}"))
        return payload

    def _paged(self, path, **params):
        payload = self._request("GET", path, **params)
        yield from payload.get("data", [])
        next_url = payload.get("paging", {}).get("next")
        while next_url:
            try:
                response = self.session.get(next_url, timeout=30)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise AdapterError(f"Meta pagination failed: {exc}") from exc
            payload = response.json()
            yield from payload.get("data", [])
            next_url = payload.get("paging", {}).get("next")

    def list_accounts(self):
        return [
            RemoteAccount(
                external_id=row["account_id"],
                name=row.get("name") or row["account_id"],
                currency=row.get("currency", "INR"),
                timezone=row.get("timezone_name", "Asia/Kolkata"),
            )
            for row in self._paged("me/adaccounts", fields="account_id,name,currency,timezone_name", limit=100)
        ]

    def list_campaigns(self, account):
        fields = "id,name,objective,status,daily_budget,lifetime_budget,start_time,stop_time"
        return [
            RemoteCampaign(
                external_id=row["id"],
                name=row.get("name", row["id"]),
                status=STATUS_MAP.get(row.get("status", ""), CampaignStatus.ERROR),
                objective=row.get("objective", "").replace("OUTCOME_", "").title(),
                daily_budget_paise=_minor_units_to_paise(row.get("daily_budget")),
                lifetime_budget_paise=_minor_units_to_paise(row.get("lifetime_budget")),
                start_date=_parse_date(row.get("start_time")),
                end_date=_parse_date(row.get("stop_time")),
            )
            for row in self._paged(f"act_{account.external_id}/campaigns", fields=fields, limit=200)
        ]

    def fetch_daily_metrics(self, account, start, end):
        rows = []
        params = {
            "level": "campaign",
            "time_increment": 1,
            "fields": "campaign_id,date_start,spend,impressions,clicks,reach,actions,action_values",
            "time_range": f'{{"since":"{start.isoformat()}","until":"{end.isoformat()}"}}',
            "limit": 500,
        }
        for row in self._paged(f"act_{account.external_id}/insights", **params):
            actions = {a["action_type"]: float(a["value"]) for a in row.get("actions", [])}
            values = {a["action_type"]: float(a["value"]) for a in row.get("action_values", [])}
            leads = int(sum(v for k, v in actions.items() if k in LEAD_ACTION_TYPES))
            purchases = int(sum(v for k, v in actions.items() if k in PURCHASE_ACTION_TYPES))
            revenue = sum(v for k, v in values.items() if k in PURCHASE_ACTION_TYPES)
            rows.append(
                RemoteMetricRow(
                    campaign_external_id=row["campaign_id"],
                    date=date.fromisoformat(row["date_start"]),
                    spend_paise=rupees_to_paise(row.get("spend", 0)),
                    impressions=int(row.get("impressions", 0)),
                    clicks=int(row.get("clicks", 0)),
                    reach=int(row["reach"]) if row.get("reach") else None,
                    leads=leads,
                    conversions=leads + purchases,
                    revenue_paise=rupees_to_paise(revenue) if values else None,
                )
            )
        return rows

    def pause_campaign(self, campaign):
        self.require(Capability.PAUSE)
        self._request("POST", campaign.external_id, status="PAUSED")

    def resume_campaign(self, campaign):
        self.require(Capability.RESUME)
        self._request("POST", campaign.external_id, status="ACTIVE")
