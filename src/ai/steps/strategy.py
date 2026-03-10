"""Step 08c - Classify entry into balance strategies; update StrategyTracking.

Six deterministic detectors run in priority order; at most 2 are credited
(top-2 cap). StrategyTracking.usage_count is incremented for each credited
strategy so variety.py can compute the Shannon-entropy variety score next run.

Architecture reference: sections 5.2.2-5.2.7.
"""

from __future__ import annotations
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from sqlalchemy.orm import Session
from src.db.models.harmony import HarmonyDimension
from src.db.models.journal_entry import JournalEntry
from src.db.models.strategy import StrategyTracking

logger = logging.getLogger(__name__)

STRATEGY_KEYS = ("social", "study", "mundane", "troll", "grind", "harmony")

_SOCIAL_KW = (
    "meeting",
    "presentation",
    "networking",
    "group",
    "team",
    "public",
    "stranger",
    "colleagues",
    "conference",
    "interview",
    "collaboration",
    "audience",
    "community",
)
_MUNDANE_KW = (
    "clean",
    "laundry",
    "chore",
    "grocery",
    "errand",
    "bill",
    "paperwork",
    "appointment",
    "maintenance",
    "organize",
    "dishes",
    "emails",
    "admin",
    "tax",
    "budget",
)
_LEARNING_KW = (
    "learn",
    "study",
    "read",
    "practice",
    "course",
    "lecture",
    "tutorial",
    "research",
    "review",
    "drill",
    "training",
)
_LEARNING_TYPES = frozenset(["analytical", "intellectual"])


def _coerce_int(value: object) -> int:
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_social_risk(content: str, goal_relation: str | None) -> bool:
    """Sec 5.2.2: social keywords AND goal_relation indicates first time."""
    text = content.lower()
    if not any(kw in text for kw in _SOCIAL_KW):
        return False
    if not goal_relation:
        return False
    return "first" in goal_relation.lower()


def _is_study_burst(
    user_id: str, content: str, task_type: str | None, db: Session
) -> bool:
    """Sec 5.2.3: entry is part of a >=3 learning-candidate burst within 7 days."""
    cutoff = _now_utc() - timedelta(days=7)
    rows = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.user_id == user_id,
            JournalEntry.status == "completed",
            JournalEntry.created_at >= cutoff,
        )
        .all()
    )

    def _candidate(e: JournalEntry) -> bool:
        text = (e.content or "").lower()
        return any(kw in text for kw in _LEARNING_KW) or (
            (e.entry_type or "").lower() in _LEARNING_TYPES
        )

    this_text = content.lower()
    this_ok = any(kw in this_text for kw in _LEARNING_KW) or (
        (task_type or "").lower() in _LEARNING_TYPES
    )
    if not this_ok:
        return False
    return sum(1 for r in rows if _candidate(r)) + 1 >= 3


def _is_mundane_focus(
    content: str, task_type: str | None, energy_level: int | None
) -> bool:
    """Sec 5.2.4: mundane keywords OR routine task type with low energy."""
    if any(kw in content.lower() for kw in _MUNDANE_KW):
        return True
    tt = (task_type or "").lower()
    return (
        tt in ("practical", "administrative")
        and energy_level is not None
        and int(energy_level) <= 5
    )


def _is_troll_exploits(anomaly_score: float) -> bool:
    """Sec 5.2.5: anomaly_score >= 0.70 (equivalent to 7.0 on 0-10 arch scale)."""
    return float(anomaly_score) >= 0.70


def _is_daily_grind(user_id: str, db: Session) -> bool:
    """Sec 5.2.6: completed entries exist on each of the last 2 UTC calendar days."""
    now = _now_utc()
    for days_back in (1, 2):
        target = now - timedelta(days=days_back)
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        if (
            db.query(JournalEntry)
            .filter(
                JournalEntry.user_id == user_id,
                JournalEntry.status == "completed",
                JournalEntry.created_at >= day_start,
                JournalEntry.created_at < day_start + timedelta(days=1),
            )
            .count()
            == 0
        ):
            return False
    return True


def _is_harmony_balance(user_id: str, db: Session) -> bool:
    """Sec 5.2.7: user's lowest HarmonyDimension.score < 0.50."""
    rows = db.query(HarmonyDimension).filter(HarmonyDimension.user_id == user_id).all()
    return bool(rows) and min(r.score for r in rows) < 0.50


# ---------------------------------------------------------------------------
# Diminishing returns (architecture §5.9)
# ---------------------------------------------------------------------------


def diminishing_multiplier_from_streaks(
    credited_strategies: list[str],
    streaks_json: str,
    yesterday_local: date,
) -> float:
    """Compute the diminishing-returns multiplier from strategy streak state.

    Architecture reference: §5.9.3–5.9.5 (normative reference implementation).

    Args:
        credited_strategies: Top-2 credited strategy names for the current entry.
        streaks_json:        JSON string from StrategyTracking.strategy_streaks_json.
        yesterday_local:     User-local yesterday date (UTC proxy when tz unknown).

    Returns:
        Float multiplier in [0.75, 1.0].
        s=0–2  → 1.00;  s=3 → 0.95;  s=7+ → 0.75 (floor).
    """
    try:
        streaks: dict[str, dict[str, object]] = json.loads(streaks_json or "{}")
    except Exception:
        streaks = {}

    def streak_count(sk: str) -> int:
        v = streaks.get(sk) or {}
        last_day = v.get("last_day")
        if last_day != yesterday_local.isoformat():
            return 0
        return _coerce_int(v.get("count") or 0)

    s = max((streak_count(sk) for sk in credited_strategies), default=0)
    mult = 1.0 - 0.05 * max(0, s - 2)
    return float(max(0.75, mult))


def _update_strategy_streaks(
    *, user_id: str, credited_strategies: list[str], db: Session
) -> None:
    """Incrementally extend strategy_streaks_json for today's credited strategies.

    Uses UTC date as a proxy for user-local date (no per-user timezone in sync
    pipeline).  For each credited strategy:
    - If last_day == today  → already recorded this calendar day; no change.
    - If last_day == yesterday → consecutive day; increment count.
    - Otherwise             → new streak starting today (count=1).
    """
    if not credited_strategies:
        return

    row = db.query(StrategyTracking).filter(StrategyTracking.user_id == user_id).first()
    if row is None:
        return

    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    today_iso = today.isoformat()
    yesterday_iso = yesterday.isoformat()

    try:
        streaks: dict[str, dict[str, object]] = json.loads(
            row.strategy_streaks_json or "{}"
        )
    except Exception:
        streaks = {}

    for sk in credited_strategies:
        v = streaks.get(sk) or {}
        last_day = v.get("last_day")
        if last_day == today_iso:
            continue  # already credited today
        if last_day == yesterday_iso:
            streaks[sk] = {
                "count": _coerce_int(v.get("count") or 0) + 1,
                "last_day": today_iso,
            }
        else:
            streaks[sk] = {"count": 1, "last_day": today_iso}

    row.strategy_streaks_json = json.dumps(
        streaks, separators=(",", ":"), sort_keys=True
    )


def run(
    *,
    user_id: str,
    canonical_text: str,
    detection: dict[str, Any],
    anomaly_score: float,
    db: Session,
    goal_relation: str | None = None,
) -> dict[str, Any]:
    """Classify the current entry into balance strategies and update StrategyTracking.

    Reads strategy_streaks_json BEFORE crediting the current entry (so diminishing
    returns reflects yesterday's streaks — architecture §5.9 "today affects tomorrow").
    After crediting, updates streaks with today's strategies for future entries.

    Args:
        user_id:        Owning user UUID.
        canonical_text: Normalised entry text (step 03 output).
        detection:      Signal-detection output from step 07.
        anomaly_score:  0-1 normalised score from step 08b precheck.
        db:             SQLAlchemy session (write - issues flushes).
        goal_relation:  Optional goal_relation from journal_entries_structured.

    Returns:
        Dict with keys:
            detected_strategies  -- list of up to 2 credited strategy names.
            strategy_scores      -- dict mapping each strategy to True/False.
            diminishing_multiplier -- float [0.75, 1.0] from §5.9.3.
            diminishing_bp       -- int basis points (7500–10000).
    """
    task_type: str | None = detection.get("task_type")
    energy_level: int | None = detection.get("energy_level")

    # Read streak state BEFORE crediting today's entry (§5.9 "today affects tomorrow").
    tracking_row = (
        db.query(StrategyTracking).filter(StrategyTracking.user_id == user_id).first()
    )
    streaks_json: str = getattr(tracking_row, "strategy_streaks_json", None) or "{}"
    yesterday_local: date = datetime.now(timezone.utc).date() - timedelta(days=1)

    detectors = {
        "social": lambda: _is_social_risk(canonical_text, goal_relation),
        "study": lambda: _is_study_burst(user_id, canonical_text, task_type, db),
        "mundane": lambda: _is_mundane_focus(canonical_text, task_type, energy_level),
        "troll": lambda: _is_troll_exploits(anomaly_score),
        "grind": lambda: _is_daily_grind(user_id, db),
        "harmony": lambda: _is_harmony_balance(user_id, db),
    }

    strategy_scores: dict[str, bool] = {}
    for key in STRATEGY_KEYS:
        try:
            strategy_scores[key] = detectors[key]()
        except Exception:
            logger.exception("strategy detector failed key=%s; defaulting False", key)
            strategy_scores[key] = False

    # Top-2 cap in priority order.
    detected_strategies = [k for k in STRATEGY_KEYS if strategy_scores.get(k)][:2]

    # Compute diminishing multiplier from yesterday's streaks (before today updates them).
    diminishing_multiplier = diminishing_multiplier_from_streaks(
        detected_strategies, streaks_json, yesterday_local
    )
    diminishing_bp = int(diminishing_multiplier * 10000)

    for name in detected_strategies:
        _increment_strategy_count(user_id=user_id, strategy_name=name, db=db)

    # Update streak state for today (future entries see this data as "yesterday").
    _update_strategy_streaks(
        user_id=user_id, credited_strategies=detected_strategies, db=db
    )
    db.flush()

    return {
        "detected_strategies": detected_strategies,
        "strategy_scores": strategy_scores,
        "diminishing_multiplier": diminishing_multiplier,
        "diminishing_bp": diminishing_bp,
    }


def _increment_strategy_count(*, user_id: str, strategy_name: str, db: Session) -> None:
    """Upsert and increment StrategyTracking.usage_count for the given strategy."""
    now = _now_utc()
    row = (
        db.query(StrategyTracking)
        .filter(
            StrategyTracking.user_id == user_id,
            StrategyTracking.strategy_name == strategy_name,
        )
        .one_or_none()
    )
    if row is None:
        db.add(
            StrategyTracking(
                user_id=user_id,
                strategy_name=strategy_name,
                usage_count=1,
                success_rate=0.0,
                updated_at=now,
            )
        )
    else:
        row.usage_count += 1
        row.updated_at = now
