"""
Manual job trigger endpoints.

Provides HTTP endpoints for triggering background jobs on demand
and inspecting scheduler state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.jobs.daily_decay_job import DailyDecayJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/decay/run", summary="Trigger daily decay job")
async def trigger_decay_job(
    user_id: Optional[str] = Query(None, description="Run for specific user (omit for all users)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Manually trigger the daily decay job.

    Useful for testing and manual execution without waiting for the
    2 AM UTC scheduled run.
    """
    job = DailyDecayJob(db)
    now_utc = datetime.now(timezone.utc)

    if user_id:
        result = await job.run_for_user(user_id, now_utc)
        return {"status": "success", "type": "single_user", "result": result}

    summary = await job.run_for_all_users(now_utc)
    return {"status": "success", "type": "all_users", "summary": summary}


@router.get("/decay/status", summary="Decay scheduler status")
def get_decay_status() -> Dict[str, Any]:
    """Return current scheduler state and next scheduled run times."""
    from src.jobs.scheduler import scheduler

    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
            }
        )

    return {
        "scheduler_running": scheduler.running,
        "jobs": jobs_info,
    }
