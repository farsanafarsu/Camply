import logging

from celery import shared_task

from .adapters import AdapterError
from .models import AdAccount
from .services import sync_account

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def sync_account_task(self, account_id: str):
    account = AdAccount.objects.select_related("organization", "connection").get(pk=account_id)
    try:
        return sync_account(account)
    except AdapterError as exc:
        logger.warning("Sync failed for ad account %s: %s", account_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task
def sync_all_accounts():
    ids = AdAccount.objects.filter(is_manual=False).values_list("pk", flat=True)
    for account_id in ids:
        sync_account_task.delay(str(account_id))
    return len(ids)
