"""Harmony refresh service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from src.core.harmony_scoring_service import HarmonyScoringService, OverworkStatus
from src.db.models.harmony import HarmonyDimension, HarmonySnapshot
from src.db.models.user import User

_DIMS = ("physical", "mental", "social", "productivity", "rest", "growth", "creative")
_FALLBACK_TZ = "UTC"


@dataclass(frozen=True)
class HarmonyRefreshResult:
    harmony: HarmonyDimension
    overwork: OverworkStatus
    snapshot_date_local: date


class HarmonyRefreshService:
    """Refresh harmony dimensions and provide read/write overwork semantics."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.scoring_service = HarmonyScoringService(db)

    def refresh_harmony(
        self,
        user_id: str,
        now_utc: datetime,
        advance_overwork_state: bool = True,
    ) -> HarmonyRefreshResult:
        normalized_now = self._normalize_now(now_utc)
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        tz = self._user_tz(user.timezone)
        today_local = normalized_now.astimezone(tz).date()
        window_end_utc = normalized_now
        window_start_utc = normalized_now - timedelta(days=7)

        harmony = (
            self.db.query(HarmonyDimension)
            .filter(HarmonyDimension.user_id == user_id)
            .one_or_none()
        )
        if harmony is None:
            harmony = HarmonyDimension(user_id=user_id)
            self.db.add(harmony)
            self.db.flush()

        metrics = self.scoring_service.calculate_window_metrics(
            user_id,
            window_start_utc,
            window_end_utc,
        )
        for dim in _DIMS:
            setattr(
                harmony,
                dim,
                self.scoring_service.round_half_up(metrics.dimension_scores[dim], 5),
            )
        harmony.overall_balance = self.scoring_service.round_half_up(
            self.scoring_service.calculate_overall_balance(
                {dim: getattr(harmony, dim) for dim in _DIMS}
            ),
            5,
        )
        harmony.updated_at = normalized_now
        self.db.flush()

        if advance_overwork_state:
            overwork = self.scoring_service.advance_overwork_state(
                harmony,
                user_id=user_id,
                today_local=today_local,
                now_utc=normalized_now,
                average_energy=metrics.average_energy,
            )
        else:
            preset = self.scoring_service.config_service.get_or_create_config(user_id).preset
            overwork = self.scoring_service.get_read_only_overwork_status(
                harmony,
                average_energy=metrics.average_energy,
                preset=preset,
            )

        self.db.flush()
        return HarmonyRefreshResult(
            harmony=harmony,
            overwork=overwork,
            snapshot_date_local=today_local - timedelta(days=1),
        )

    def create_snapshot(
        self,
        user_id: str,
        snapshot_date: date,
    ) -> HarmonySnapshot:
        harmony = (
            self.db.query(HarmonyDimension)
            .filter(HarmonyDimension.user_id == user_id)
            .one_or_none()
        )
        dim_values = harmony.dim_scores() if harmony is not None else {d: 0.5 for d in _DIMS}
        overall = harmony.overall_balance if harmony is not None else 0.5

        snapshot = (
            self.db.query(HarmonySnapshot)
            .filter(
                HarmonySnapshot.user_id == user_id,
                HarmonySnapshot.snapshot_date == snapshot_date,
            )
            .one_or_none()
        )
        if snapshot is None:
            snapshot = HarmonySnapshot(
                user_id=user_id,
                snapshot_date=snapshot_date,
                overall_balance=overall,
                **dim_values,
            )
            self.db.add(snapshot)
        else:
            for dim in _DIMS:
                setattr(snapshot, dim, dim_values[dim])
            snapshot.overall_balance = overall

        self.db.flush()
        return snapshot

    def user_local_today(self, user_id: str, now_utc: datetime) -> date:
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        return self._normalize_now(now_utc).astimezone(self._user_tz(user.timezone)).date()

    @staticmethod
    def _normalize_now(now_utc: datetime) -> datetime:
        if now_utc.tzinfo is None:
            return now_utc.replace(tzinfo=timezone.utc)
        return now_utc.astimezone(timezone.utc)

    @staticmethod
    def _user_tz(tz_name: str | None) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name or _FALLBACK_TZ)
        except (ZoneInfoNotFoundError, KeyError):
            return ZoneInfo(_FALLBACK_TZ)

    @staticmethod
    def _local_midnight_utc(day_local: date, tz: ZoneInfo) -> datetime:
        return datetime.combine(day_local, time.min, tzinfo=tz).astimezone(timezone.utc)
