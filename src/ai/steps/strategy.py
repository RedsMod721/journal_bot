"""Step 08c - Classify entry into balance strategies; update StrategyTracking.

Six deterministic detectors run in priority order; at most 2 are credited
(top-2 cap). The named count column on the StrategyTracking row is incremented
for each credited strategy so variety.py can compute the Shannon-entropy
variety score on the next run.

Architecture reference: sections 5.2.2-5.2.7.
"""

from __future__ import annotations
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from sqlalchemy.orm import Session
from src.core.harmony_classifier import HarmonyClassifier
from src.db.models.harmony import HarmonyDimension
from src.db.models.insight import Pattern
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User

logger = logging.getLogger(__name__)

STRATEGY_KEYS = ("social", "study", "mundane", "troll", "grind", "harmony")

# Maps internal strategy key → StrategyTracking column name (architecture §5.0.3).
_STRATEGY_COLUMN_MAP: dict[str, str] = {
    "social": "social_risk_count",
    "study": "study_burst_count",
    "mundane": "mundane_focus_count",
    "troll": "troll_exploits_count",
    "grind": "daily_grind_count",
    "harmony": "harmony_balance_count",
}

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
    "course",
    "lecture",
    "tutorial",
    "research",
    "review",
    "lesson",
)
_LEARNING_TYPES = frozenset(["analytical", "intellectual"])
_LEARNING_ACTIVITY_KEYS = frozenset(["study", "read", "code"])


def _coerce_int(value: object) -> int:
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _has_solo_preference(user_id: str, db: Session) -> bool:
    return (
        db.query(Pattern)
        .filter(
            Pattern.user_id == user_id,
            Pattern.pattern_type == "behavioral",
            Pattern.pattern_key.ilike("%prefers_solo%"),
        )
        .count()
        > 0
    )


def _is_social_risk(
    user_id: str,
    content: str,
    goal_relation: str | None,
    db: Session,
) -> bool:
    """Sec 5.2.2: social keywords AND goal_relation indicates first time."""
    text = content.lower()
    if not any(kw in text for kw in _SOCIAL_KW):
        return False
    first_time = bool(goal_relation) and "first" in goal_relation.lower()
    return first_time or _has_solo_preference(user_id, db)


def _is_learning_candidate(
    content: str,
    task_type: str | None,
    detected_activities: list[str] | tuple[str, ...] | None = None,
) -> bool:
    text = content.lower()
    activity_set = set(detected_activities or [])
    return bool(activity_set.intersection(_LEARNING_ACTIVITY_KEYS)) or any(
        kw in text for kw in _LEARNING_KW
    ) or ((task_type or "").lower() in _LEARNING_TYPES)


def _is_study_burst(
    user_id: str,
    entry_id: str,
    entry_created_at: datetime,
    content: str,
    task_type: str | None,
    detected_activities: list[str] | tuple[str, ...] | None,
    db: Session,
) -> bool:
    """Sec 5.2.3: entry is part of a >=3 learning-candidate burst within 7 days."""
    rows = (
        db.query(JournalEntry, JournalEntryStructured)
        .outerjoin(
            JournalEntryStructured,
            (JournalEntryStructured.user_id == JournalEntry.user_id)
            & (JournalEntryStructured.entry_id == JournalEntry.id),
        )
        .filter(
            JournalEntry.user_id == user_id,
            JournalEntry.status == "completed",
            JournalEntry.created_at >= entry_created_at - timedelta(days=7),
            JournalEntry.created_at <= entry_created_at + timedelta(days=7),
        )
        .all()
    )

    candidates = sorted(
        [
            (entry.id, entry.created_at)
            for entry, structured in rows
            if entry.created_at is not None
            and _is_learning_candidate(
                entry.content or "",
                structured.task_type if structured is not None else None,
            )
        ]
        + (
            [(entry_id, entry_created_at)]
            if _is_learning_candidate(content, task_type, detected_activities)
            else []
        ),
        key=lambda item: item[1],
    )
    if not _is_learning_candidate(content, task_type, detected_activities):
        return False
    queue: list[tuple[str, datetime]] = []
    members: set[str] = set()
    for candidate_id, created_at in candidates:
        queue.append((candidate_id, created_at))
        while queue and (created_at - queue[0][1]) > timedelta(days=7):
            queue.pop(0)
        if len(queue) >= 3:
            members.update(candidate_id for candidate_id, _ in queue)
    return entry_id in members


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


def _is_daily_grind(
    user_id: str,
    entry_created_at: datetime,
    db: Session,
) -> bool:
    """Sec 5.2.6: current local day plus the previous two local days have entries."""
    user = db.query(User).filter(User.id == user_id).one_or_none()
    tz = timezone.utc if user is None else _user_tz(user.timezone)
    entry_day = entry_created_at.astimezone(tz).date()
    rows = (
        db.query(JournalEntry.created_at)
        .filter(
            JournalEntry.user_id == user_id,
            JournalEntry.status == "completed",
            JournalEntry.created_at >= entry_created_at - timedelta(days=3),
            JournalEntry.created_at <= entry_created_at,
        )
        .all()
    )
    local_days = {
        created_at.astimezone(tz).date()
        for (created_at,) in rows
        if created_at is not None
    }
    local_days.add(entry_day)
    return all((entry_day - timedelta(days=offset)) in local_days for offset in (0, 1, 2))


def _is_harmony_balance(
    user_id: str,
    db: Session,
    *,
    task_type: str | None = None,
    content: str = "",
    skills_themes_involved: str | None = None,
) -> bool:
    """Sec 5.2.7: entry addresses the user's current lowest low dimension."""
    row = db.query(HarmonyDimension).filter(HarmonyDimension.user_id == user_id).first()
    if row is None:
        return False

    dim_scores = row.dim_scores()
    lowest_dimension = min(dim_scores, key=dim_scores.get)
    if dim_scores[lowest_dimension] >= 0.50:
        return False

    classifier = HarmonyClassifier(db)
    structured = type(
        "_StructuredProxy",
        (),
        {
            "task_type": task_type,
            "skills_themes_involved": skills_themes_involved,
        },
    )()
    entry = type("_EntryProxy", (), {"content": content, "user_id": user_id})()
    return lowest_dimension in classifier.classify_dimensions(entry, structured)


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
    entry_id: str,
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
    detected_activities = list(detection.get("detected_activities", []) or [])
    entry_row = (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id, JournalEntry.id == entry_id)
        .one_or_none()
    )
    entry_created_at = (
        entry_row.created_at if entry_row is not None and entry_row.created_at is not None else _now_utc()
    )

    # Read streak state BEFORE crediting today's entry (§5.9 "today affects tomorrow").
    tracking_row = (
        db.query(StrategyTracking).filter(StrategyTracking.user_id == user_id).first()
    )
    streaks_json: str = getattr(tracking_row, "strategy_streaks_json", None) or "{}"
    yesterday_local: date = datetime.now(timezone.utc).date() - timedelta(days=1)

    detectors = {
        "social": lambda: _is_social_risk(user_id, canonical_text, goal_relation, db),
        "study": lambda: _is_study_burst(
            user_id,
            entry_id,
            entry_created_at,
            canonical_text,
            task_type,
            detected_activities,
            db,
        ),
        "mundane": lambda: _is_mundane_focus(canonical_text, task_type, energy_level),
        "troll": lambda: _is_troll_exploits(anomaly_score),
        "grind": lambda: _is_daily_grind(user_id, entry_created_at, db),
        "harmony": lambda: _is_harmony_balance(
            user_id,
            db,
            task_type=task_type,
            content=canonical_text,
            skills_themes_involved=None,
        ),
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
        "provenance": {
            "detector_order": list(STRATEGY_KEYS),
            "task_type": task_type,
            "detected_activities": detected_activities,
            "study_requires": "explicit learning activity, learning keywords, or intellectual task burst",
            "fired_strategies": detected_strategies,
        },
    }


def _user_tz(tz_name: str | None) -> timezone:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, KeyError):
        return timezone.utc


def _increment_strategy_count(*, user_id: str, strategy_name: str, db: Session) -> None:
    """Upsert the single StrategyTracking row and increment the named count column.

    Architecture §5.0.3: one row per user; each of the six strategies has its
    own count column (e.g. social_risk_count, study_burst_count, …).
    """
    col_name = _STRATEGY_COLUMN_MAP.get(strategy_name)
    if not col_name:
        logger.warning("_increment_strategy_count: unknown strategy_name=%r", strategy_name)
        return

    now = _now_utc()
    row = (
        db.query(StrategyTracking)
        .filter(StrategyTracking.user_id == user_id)
        .one_or_none()
    )
    if row is None:
        today = now.date()
        kwargs: dict[str, object] = {col_name: 1}
        db.add(
            StrategyTracking(
                user_id=user_id,
                strategy_streaks_json="{}",
                window_start_date=today - timedelta(days=30),
                window_end_date=today,
                updated_at=now,
                **kwargs,
            )
        )
    else:
        current = int(getattr(row, col_name, 0) or 0)
        setattr(row, col_name, current + 1)
        row.updated_at = now
