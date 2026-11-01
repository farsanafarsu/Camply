from celery import shared_task

from .engine import run_rules


@shared_task
def evaluate_all_rules():
    return len(run_rules())
