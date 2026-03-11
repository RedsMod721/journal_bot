"""Balance system rolling window refresh."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from src.ai.steps.variety import _STRATEGY_COUNT_COLUMNS
from src.core.balance_strategy_detector import StrategyDetector
from src.core.balance_variety_service import VarietyService
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User

logger = logging.getLogger(__name__)

_FALLBACK_TZ = "UTC"
_STREAK_LOOKBACK_DAYS = 30
_EXTENDED_LOOKBACK_DAYS = 7


def _normalize_now(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        return now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(timezone.utc)


def _user_tz(user: User) -> ZoneInfo:
    tz_name: str = getattr(user, "timezone", None) or _FALLBACK_TZ
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo(_FALLBACK_TZ)


def _local_midnight_utc(day_local: date, tz: ZoneInfo) -> datetime:
    return (
        datetime.combine(day_local, time.min, tzinfo=tz)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )


def _window_boundaries(now_utc: datetime, tz: ZoneInfo) -> tuple[date, date, datetime, datetime]:
    normalized = _normalize_now(now_utc)
    today_local = normalized.astimezone(tz).date()
    window_end_date = today_local
    window_start_date = today_local - timedelta(days=30)
    return (
        window_start_date,
        window_end_date,
        _local_midnight_utc(window_start_date, tz),
        _local_midnight_utc(window_end_date, tz),
    )


def _day_key(timestamp: datetime, tz: ZoneInfo) -> date:
    ts = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)
    return ts.astimezone(tz).date()


def _compute_strategy_streaks_json(day_used: dict[date, set[str]], yesterday_local: date) -> str:
    streaks: dict[str, dict[str, object]] = {}
    for key in _STRATEGY_COUNT_COLUMNS:
        if key not in day_used.get(yesterday_local, set()):
            continue
        count = 1
        for offset in range(1, _STREAK_LOOKBACK_DAYS):
            day = yesterday_local - timedelta(days=offset)
            if key in day_used.get(day, set()):
                count += 1
            else:
                break
        streaks[key] = {"count": count, "last_day": yesterday_local.isoformat()}
    return json.dumps(streaks, separators=(",", ":"), sort_keys=True)


class BalanceWindowService:
    """Refresh the rolling 30-day strategy window."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.detector = StrategyDetector(db)
        self.variety_service = VarietyService(db)

    def refresh_window(self, user_id: str, now_utc: datetime) -> StrategyTracking:
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        tz = _user_tz(user)
        (
            window_start_date,
            window_end_date,
            window_start_utc,
            window_end_utc,
        ) = _window_boundaries(now_utc, tz)
        extended_start_utc = _local_midnight_utc(
            window_start_date - timedelta(days=_EXTENDED_LOOKBACK_DAYS),
            tz,
        )

        tracking = self._get_or_create_tracking(user_id, window_start_date, window_end_date)
        tracking.window_start_date = window_start_date
        tracking.window_end_date = window_end_date
        for col in _STRATEGY_COUNT_COLUMNS.values():
            setattr(tracking, col, 0)

        rows: list[tuple[JournalEntry, JournalEntryStructured | None]] = (
            self.db.query(JournalEntry, JournalEntryStructured)
            .outerjoin(
                JournalEntryStructured,
                (JournalEntryStructured.user_id == JournalEntry.user_id)
                & (JournalEntryStructured.entry_id == JournalEntry.id),
            )
            .filter(
                JournalEntry.user_id == user_id,
                JournalEntry.status == "completed",
                JournalEntry.created_at >= extended_start_utc,
                JournalEntry.created_at < window_end_utc,
            )
            .order_by(JournalEntry.created_at.asc())
            .all()
        )

        missing_structured_in_window = False
        day_used: dict[date, set[str]] = {}

        for entry, structured in rows:
            created_at = entry.created_at
            if created_at is None:
                continue

            if structured is None and created_at >= window_start_utc:
                missing_structured_in_window = True
                continue

            if created_at < window_start_utc:
                continue

            detected = self.detector.detect_strategies(
                user_id=user_id,
                entry_id=entry.id,
                entry=entry,
                structured=structured,
            )
            self._apply_strategy_increments(tracking, detected)

            if detected:
                entry_day = _day_key(created_at, tz)
                day_used.setdefault(entry_day, set()).update(detected)

        variety_score, variety_bonus_pct = self.variety_service.update_variety_metrics(
            user_id=user_id,
            tracking=tracking,
        )

        if missing_structured_in_window:
            logger.warning(
                "Balance refresh fail-safe triggered: missing structured rows in 30-day window",
                extra={"user_id": user_id},
            )
            tracking.variety_score = 0.0
            tracking.variety_bonus_pct = 0.0
            variety_score = 0.0
            variety_bonus_pct = 0.0

        tracking.strategy_streaks_json = _compute_strategy_streaks_json(
            day_used,
            yesterday_local=window_end_date - timedelta(days=1),
        )
        tracking.updated_at = _normalize_now(now_utc)
        self.db.commit()

        return tracking

    def increment_strategy(
        self,
        user_id: str,
        strategies: list[str],
        now_utc: datetime,
    ) -> StrategyTracking:
        tracking = (
            self.db.query(StrategyTracking)
            .filter(StrategyTracking.user_id == user_id)
            .one_or_none()
        )
        if tracking is None:
            return self.refresh_window(user_id, now_utc)

        self._apply_strategy_increments(tracking, strategies)
        self.variety_service.update_variety_metrics(user_id=user_id, tracking=tracking)
        self.db.commit()
        return tracking

    def _get_or_create_tracking(
        self,
        user_id: str,
        window_start_date: date,
        window_end_date: date,
    ) -> StrategyTracking:
        tracking = (
            self.db.query(StrategyTracking)
            .filter(StrategyTracking.user_id == user_id)
            .one_or_none()
        )
        if tracking is None:
            tracking = StrategyTracking(
                user_id=user_id,
                window_start_date=window_start_date,
                window_end_date=window_end_date,
            )
            self.db.add(tracking)
            self.db.flush()
        return tracking

    @staticmethod
    def _apply_strategy_increments(
        tracking: StrategyTracking,
        strategies: list[str],
    ) -> None:
        for key in strategies:
            col = _STRATEGY_COUNT_COLUMNS.get(key)
            if col is not None:
                setattr(tracking, col, int(getattr(tracking, col) or 0) + 1)
