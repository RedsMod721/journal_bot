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
SCHEDULE_CADENCE_MINUTES = 15
LOCAL_CUTOFF_HOUR = 0
LOCAL_CUTOFF_MINUTE = 15


def init_scheduler() -> None:
    """Initialize and start the scheduler with all registered jobs."""
    if scheduler.running:
        logger.info("Scheduler already running; skipping re-initialization")
        return

    # Run every 15 minutes; the job itself selects users whose local clock is
    # past 00:15 and who have not already completed maintenance for that day.
    scheduler.add_job(
        run_daily_decay_job,
        CronTrigger(minute=f"*/{SCHEDULE_CADENCE_MINUTES}"),
        id="daily_decay",
        name="Daily Week 5 Maintenance",
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
