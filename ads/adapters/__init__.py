from django.conf import settings

from ..models import Platform
from .base import (
    AdapterError,
    AdPlatformAdapter,
    AuthExpired,
    Capability,
    NotConfigured,
    UnsupportedAction,
)
from .meta import MetaAdapter
from .pending import GoogleAdsAdapter, OpenAIAdsAdapter, TikTokAdsAdapter
from .sandbox import SandboxAdapter

ADAPTERS: dict[str, type[AdPlatformAdapter]] = {
    Platform.META: MetaAdapter,
    Platform.GOOGLE: GoogleAdsAdapter,
    Platform.TIKTOK: TikTokAdsAdapter,
    Platform.OPENAI: OpenAIAdsAdapter,
}


def adapter_for_account(account) -> AdPlatformAdapter:
    """Pick the adapter for an ad account.

    Accounts with a live connection use the real platform adapter. Accounts without one
    use the sandbox adapter when CAMPLY_SANDBOX_ADAPTERS is on (development and demos).
    """
    if account.connection_id is None:
        if settings.CAMPLY_SANDBOX_ADAPTERS:
            names = list(account.campaigns.order_by("external_id").values_list("name", flat=True)) or None
            return SandboxAdapter(platform=account.platform, campaign_names=names)
        raise NotConfigured("This ad account is not connected to its platform.")
    return ADAPTERS[account.platform](account.connection)


def capabilities_for_account(account) -> frozenset[Capability]:
    if account.is_manual:
        return frozenset()
    try:
        return adapter_for_account(account).capabilities
    except NotConfigured:
        return frozenset()


__all__ = [
    "ADAPTERS",
    "AdPlatformAdapter",
    "AdapterError",
    "AuthExpired",
    "Capability",
    "NotConfigured",
    "UnsupportedAction",
    "adapter_for_account",
    "capabilities_for_account",
]
