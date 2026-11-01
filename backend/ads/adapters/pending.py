"""Connectors that are registered but not built yet.

They exist so the rest of Camply can list the platform, show its status honestly and
accept manually reported results, without pretending live API access works.
"""

from ..models import Platform
from .base import AdPlatformAdapter, NotConfigured


class PendingAdapter(AdPlatformAdapter):
    capabilities = frozenset()
    message = ""

    def _not_ready(self):
        raise NotConfigured(self.message)

    def list_accounts(self):
        self._not_ready()

    def list_campaigns(self, account):
        self._not_ready()

    def fetch_daily_metrics(self, account, start, end):
        self._not_ready()


class GoogleAdsAdapter(PendingAdapter):
    platform = Platform.GOOGLE
    docs_url = "https://developers.google.com/google-ads/api/docs/start"
    message = "The Google Ads connector needs a Google Ads API developer token and OAuth client. Not built yet."


class TikTokAdsAdapter(PendingAdapter):
    platform = Platform.TIKTOK
    docs_url = "https://business-api.tiktok.com/portal/docs"
    message = "The TikTok Ads connector needs an approved TikTok Business API app. Not built yet."


class OpenAIAdsAdapter(PendingAdapter):
    platform = Platform.OPENAI
    docs_url = "https://developers.openai.com/ads/api-overview"
    message = "The ChatGPT Ads connector needs OpenAI Ads Advertiser API access. Not built yet."
