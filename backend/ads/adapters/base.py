"""The one interface every ad platform integration implements.

The rest of Camply talks only to `AdPlatformAdapter`; platform-specific API details stay
inside each adapter. Not every platform supports every action, so each adapter declares
its `capabilities` and the UI only offers actions the platform supports.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Capability(StrEnum):
    READ_CAMPAIGNS = "read_campaigns"
    READ_METRICS = "read_metrics"
    PAUSE = "pause"
    RESUME = "resume"
    UPDATE_BUDGET = "update_budget"
    CREATE_CAMPAIGN = "create_campaign"


CAPABILITY_LABELS = {
    Capability.READ_CAMPAIGNS: "Read campaigns",
    Capability.READ_METRICS: "Read results",
    Capability.PAUSE: "Pause",
    Capability.RESUME: "Resume",
    Capability.UPDATE_BUDGET: "Change budget",
    Capability.CREATE_CAMPAIGN: "Create campaigns",
}


class AdapterError(Exception):
    """The platform returned an error or could not be reached."""


class AuthExpired(AdapterError):
    """The connection's token is expired or revoked; the user must reconnect."""


class UnsupportedAction(AdapterError):
    """The platform (or this connection) does not allow this action."""


class NotConfigured(AdapterError):
    """The connector exists but is not set up (missing app credentials or API access)."""


@dataclass(frozen=True)
class RemoteAccount:
    external_id: str
    name: str
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"


@dataclass(frozen=True)
class RemoteCampaign:
    external_id: str
    name: str
    status: str  # one of ads.models.CampaignStatus values
    objective: str = ""
    daily_budget_paise: int | None = None
    lifetime_budget_paise: int | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class RemoteMetricRow:
    campaign_external_id: str
    date: date
    spend_paise: int
    impressions: int
    clicks: int
    leads: int = 0
    conversions: int = 0
    reach: int | None = None
    revenue_paise: int | None = None


class AdPlatformAdapter(ABC):
    platform: str = ""
    capabilities: frozenset[Capability] = frozenset()
    docs_url: str = ""

    def __init__(self, connection=None):
        self.connection = connection

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def require(self, capability: Capability):
        if not self.supports(capability):
            raise UnsupportedAction(f"{self.platform} does not support '{capability}' through Camply yet.")

    @abstractmethod
    def list_accounts(self) -> list[RemoteAccount]: ...

    @abstractmethod
    def list_campaigns(self, account) -> list[RemoteCampaign]: ...

    @abstractmethod
    def fetch_daily_metrics(self, account, start: date, end: date) -> list[RemoteMetricRow]: ...

    def pause_campaign(self, campaign) -> None:
        self.require(Capability.PAUSE)
        raise NotImplementedError

    def resume_campaign(self, campaign) -> None:
        self.require(Capability.RESUME)
        raise NotImplementedError

    def update_daily_budget(self, campaign, daily_budget_paise: int) -> None:
        self.require(Capability.UPDATE_BUDGET)
        raise NotImplementedError
