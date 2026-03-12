"""
Daily decay job for forgiveness system.

Runs once per day per user to update skill staleness and insight strength.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from src.core.balance_window_service import BalanceWindowService
from src.core.forgiveness_decay_service import ForgivenessDecayService
from src.core.harmony_refresh_service import HarmonyRefreshService
from src.db.models.forgiveness import DecaySnapshot
from src.db.models.harmony import HarmonySnapshot
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User
from src.db.session import db_session

logger = logging.getLogger(__name__)
_LOCAL_CUTOFF = time(hour=0, minute=15)
_FALLBACK_TZ = "UTC"


class DailyDecayJob:
    """Daily decay job runner."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.decay_service = ForgivenessDecayService(db)
        self.window_service = BalanceWindowService(db)
        self.harmony_service = HarmonyRefreshService(db)

    @staticmethod
    def _normalize_now(now_utc: datetime | None) -> datetime:
        if now_utc is None:
            return datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            return now_utc.replace(tzinfo=timezone.utc)
        return now_utc.astimezone(timezone.utc)

    @staticmethod
    def _user_tz(tz_name: str | None) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name or _FALLBACK_TZ)
        except (ZoneInfoNotFoundError, KeyError):
            return ZoneInfo(_FALLBACK_TZ)

    def _local_dates_for_user(
        self,
        user: User,
        now_utc: datetime,
    ) -> tuple[datetime, date, date]:
        local_now = now_utc.astimezone(self._user_tz(user.timezone))
        today_local = local_now.date()
        return local_now, today_local, today_local - timedelta(days=1)

    def _maintenance_completed_for_local_day(
        self,
        user_id: str,
        *,
        today_local: date,
        yesterday_local: date,
    ) -> bool:
        decay_exists = (
            self.db.query(DecaySnapshot.id)
            .filter(
                DecaySnapshot.user_id == user_id,
                DecaySnapshot.snapshot_date == today_local.isoformat(),
            )
            .first()
            is not None
        )
        harmony_exists = (
            self.db.query(HarmonySnapshot.user_id)
            .filter(
                HarmonySnapshot.user_id == user_id,
                HarmonySnapshot.snapshot_date == yesterday_local,
            )
            .first()
            is not None
        )
        tracking_up_to_date = (
            self.db.query(StrategyTracking.user_id)
            .filter(
                StrategyTracking.user_id == user_id,
                StrategyTracking.window_end_date == today_local,
            )
            .first()
            is not None
        )
        return decay_exists and harmony_exists and tracking_up_to_date

    def _due_status_for_user(
        self,
        user: User,
        now_utc: datetime,
    ) -> tuple[bool, str, date]:
        local_now, today_local, yesterday_local = self._local_dates_for_user(
            user, now_utc
        )
        if local_now.timetz().replace(tzinfo=None) < _LOCAL_CUTOFF:
            return False, "before_local_cutoff", today_local
        if self._maintenance_completed_for_local_day(
            user.id,
            today_local=today_local,
            yesterday_local=yesterday_local,
        ):
            return False, "already_completed_for_local_day", today_local
        return True, "due", today_local

    async def run_for_user(
        self,
        user_id: str,
        now_utc: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Run daily decay for a single user.

        Returns metrics about decay applied.
        """
        now_utc = self._normalize_now(now_utc)

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

    async def run_for_due_users(
        self,
        now_utc: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Run daily maintenance only for users whose local day is eligible.

        A user is eligible once their local clock is past 00:15 and the
        previous scheduled run for that local day has not already completed.
        """
        now_utc = self._normalize_now(now_utc)
        logger.info("Running scheduled daily maintenance for due users")

        users = self.db.query(User).all()
        summary: Dict[str, Any] = {
            "timestamp": now_utc.isoformat(),
            "total_users": len(users),
            "eligible": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
        }

        for user in users:
            is_due, reason, today_local = self._due_status_for_user(user, now_utc)
            if not is_due:
                summary["skipped"] += 1
                summary["results"].append(
                    {
                        "user_id": user.id,
                        "status": "skipped",
                        "reason": reason,
                        "local_date": today_local.isoformat(),
                    }
                )
                continue

            summary["eligible"] += 1
            try:
                result = await self.run_for_user(user.id, now_utc)
                result["status"] = "success"
                result["local_date"] = today_local.isoformat()
                summary["successful"] += 1
                summary["results"].append(result)
            except Exception as exc:
                logger.error("Failed to run decay for due user %s: %s", user.id, exc)
                summary["failed"] += 1
                summary["results"].append(
                    {
                        "user_id": user.id,
                        "status": "error",
                        "reason": str(exc),
                        "local_date": today_local.isoformat(),
                    }
                )

        logger.info(
            "Scheduled daily maintenance complete: %d eligible, %d successful, %d failed, %d skipped",
            summary["eligible"],
            summary["successful"],
            summary["failed"],
            summary["skipped"],
        )
        return summary

    async def run_for_all_users(
        self,
        now_utc: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Run daily decay for all users.

        Returns summary metrics.
        """
        now_utc = self._normalize_now(now_utc)

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
        return await job.run_for_due_users()
