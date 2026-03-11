"""
Daily decay job for forgiveness system.

Runs once per day per user to update skill staleness and insight strength.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from src.core.balance_window_service import BalanceWindowService
from src.core.forgiveness_decay_service import ForgivenessDecayService
from src.core.harmony_refresh_service import HarmonyRefreshService
from src.db.models.user import User
from src.db.session import db_session

logger = logging.getLogger(__name__)


class DailyDecayJob:
    """Daily decay job runner."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.decay_service = ForgivenessDecayService(db)
        self.window_service = BalanceWindowService(db)
        self.harmony_service = HarmonyRefreshService(db)

    async def run_for_user(
        self,
        user_id: str,
        now_utc: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Run daily decay for a single user.

        Returns metrics about decay applied.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        logger.info("Running daily decay for user %s", user_id)

        results: Dict[str, Any] = {
            "user_id": user_id,
            "timestamp": now_utc.isoformat(),
            "skills": {},
            "insights": {},
            "snapshot_created": False,
            "balance": {},
            "harmony": {},
        }

        try:
            # 1. Decay skills
            skill_metrics = self.decay_service.decay_skills(user_id, now_utc)
            results["skills"] = skill_metrics
            logger.info(
                "Decayed %d skills for user %s",
                skill_metrics["skills_decayed"],
                user_id,
            )

            # 2. Decay insights
            insight_metrics = self.decay_service.decay_insights(user_id, now_utc)
            results["insights"] = insight_metrics
            logger.info(
                "Decayed %d insights for user %s",
                insight_metrics["insights_decayed"],
                user_id,
            )

            # 3. Create forgiveness snapshot
            snapshot_date = self.decay_service.resolve_snapshot_date(user_id, now_utc)
            self.decay_service.create_decay_snapshot(user_id, snapshot_date, now_utc)
            results["snapshot_created"] = True
            logger.info(
                "Created decay snapshot for user %s on %s", user_id, snapshot_date
            )

            # 4. Refresh balance rolling window (recount 30-day strategy distribution)
            tracking = self.window_service.refresh_window(user_id, now_utc)
            results["balance"] = {
                "variety_score": float(tracking.variety_score or 0.0),
                "variety_bonus_pct": float(tracking.variety_bonus_pct or 0.0),
            }
            logger.info(
                "Refreshed balance window for user %s (variety_score=%.4f)",
                user_id,
                tracking.variety_score or 0.0,
            )

            # 5. Refresh harmony dimensions + create daily snapshot
            harmony_result = self.harmony_service.refresh_harmony(
                user_id=user_id,
                now_utc=now_utc,
                advance_overwork_state=False,  # daily job — read-only overwork status
            )
            self.harmony_service.create_snapshot(
                user_id=user_id,
                snapshot_date=harmony_result.snapshot_date_local,
            )
            self.db.commit()
            results["harmony"] = {
                "overall_balance": float(harmony_result.harmony.overall_balance or 0.5),
                "overwork_stage": int(harmony_result.harmony.overwork_stage or 0),
                "snapshot_created": True,
            }
            logger.info(
                "Refreshed harmony for user %s (overall_balance=%.4f, overwork_stage=%d)",
                user_id,
                harmony_result.harmony.overall_balance or 0.5,
                harmony_result.harmony.overwork_stage or 0,
            )

        except Exception as exc:
            logger.error("Error running daily maintenance for user %s: %s", user_id, exc)
            results["error"] = str(exc)
            raise

        return results

    async def run_for_all_users(
        self,
        now_utc: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Run daily decay for all users.

        Returns summary metrics.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        logger.info("Running daily decay for all users")

        users = self.db.query(User).all()

        summary: Dict[str, Any] = {
            "timestamp": now_utc.isoformat(),
            "total_users": len(users),
            "successful": 0,
            "failed": 0,
            "results": [],
        }

        for user in users:
            try:
                result = await self.run_for_user(user.id, now_utc)
                summary["successful"] += 1
                summary["results"].append(result)
            except Exception as exc:
                logger.error("Failed to run decay for user %s: %s", user.id, exc)
                summary["failed"] += 1
                summary["results"].append({"user_id": user.id, "error": str(exc)})

        logger.info(
            "Daily decay complete: %d successful, %d failed",
            summary["successful"],
            summary["failed"],
        )
        return summary


async def run_daily_decay_job() -> Dict[str, Any]:
    """Entrypoint for scheduled job. Opens its own DB session."""
    with db_session() as db:
        job = DailyDecayJob(db)
        return await job.run_for_all_users()
