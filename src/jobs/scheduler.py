"""
Job scheduler for recurring tasks.

Uses APScheduler for background job execution.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.jobs.daily_decay_job import run_daily_decay_job

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler() -> None:
    """Initialize and start the scheduler with all registered jobs."""
    # Daily decay — runs at 2 AM UTC every day
    scheduler.add_job(
        run_daily_decay_job,
        CronTrigger(hour=2, minute=0),
        id="daily_decay",
        name="Daily Forgiveness Decay",
        replace_existing=True,
    )

    logger.info("Scheduler initialized with jobs:")
    for job in scheduler.get_jobs():
        logger.info("  - %s (%s): %s", job.name, job.id, job.trigger)

    scheduler.start()
    logger.info("Scheduler started")


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")
