"""
Quest Matching & Completion Module
Based on Architecture Section 6 (Quest System)

Completion types:
    one_time   — single achievement; match on keywords/activity; complete at progress 1
    cumulative — accumulate a running total (e.g. word count); complete when total >= required
    recursive  — repeat N times per period; resets externally each period
    streak     — consecutive days; broken if a day is missed
"""

import json
import math
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from src.db.models.quest import Quest
from src.db.models.journal_entry import JournalEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_criteria(quest: Quest) -> tuple[Optional[dict], bool]:
    """Load matching criteria from the quest's template parameters (JSON).

    Returns:
        (criteria, parse_ok)
        - (None, True) when no criteria are configured
        - (dict, True) when criteria parse successfully
        - (None, False) when criteria were configured but malformed

    Template.parameters stores the same shape the prompt calls success_criteria:
        {"keywords": [...], "activity": "...", "skill": "...", ...}
    """
    if not quest.template or not quest.template.parameters:
        return None, True

    try:
        parsed = json.loads(quest.template.parameters)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Quest %s: could not parse template parameters", quest.id)
        return None, False
    if not isinstance(parsed, dict):
        logger.warning("Quest %s: template parameters are not a JSON object", quest.id)
        return None, False
    return parsed, True


def _skill_name(quest: Quest) -> Optional[str]:
    """Return the quest's linked skill name, or None if not loaded."""
    try:
        return quest.skill.name if quest.skill else None
    except Exception:
        return None


def _skill_matches(quest: Quest, detected_skills: list[str]) -> bool:
    """True if the quest's primary skill appears in detected_skills."""
    name = _skill_name(quest)
    if name is None:
        return False
    detected = {s.strip().lower() for s in detected_skills if isinstance(s, str)}
    return name.strip().lower() in detected


def _entry_date(entry: JournalEntry) -> Optional[datetime.date]:
    """Return entry calendar date in UTC-naive date semantics."""
    if not getattr(entry, "created_at", None):
        return None
    return entry.created_at.date()


def _quest_last_progress_date(quest: Quest) -> Optional[datetime.date]:
    """Best-effort date of the quest's latest progress mutation."""
    updated_at_utc_ms = getattr(quest, "updated_at_utc_ms", None)
    if isinstance(updated_at_utc_ms, int) and updated_at_utc_ms > 0:
        return datetime.fromtimestamp(updated_at_utc_ms / 1000, tz=timezone.utc).date()

    completed_at = getattr(quest, "completed_at", None)
    if completed_at is not None:
        return completed_at.date()

    created_at = getattr(quest, "created_at", None)
    if created_at is not None and getattr(quest, "current_progress", 0) > 0:
        return created_at.date()
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_quests(
    entry: "JournalEntry",
    user_id: str,
    detected_skills: list[str],
    detected_activities: list[str],
    db: Session,
) -> list[Quest]:
    """Return all active quests for *user_id* that match this journal entry.

    Performs a single DB query with eager-loaded skill + template to avoid
    N+1 lookups inside check_quest_match.

    Args:
        entry:               Journal entry being processed.
        user_id:             Owning user.
        detected_skills:     Skill names extracted by the AI pipeline
                             (e.g. ["Python Programming", "Cardio Running"]).
        detected_activities: Activity verbs/phrases extracted by the pipeline
                             (e.g. ["coded", "ran 5K"]).
        db:                  SQLAlchemy session.

    Returns:
        Ordered list of Quest objects that match this entry.
    """
    active_quests = (
        db.query(Quest)
        .filter(Quest.user_id == user_id, Quest.status == "active")
        .options(
            joinedload(Quest.skill),
            joinedload(Quest.template),
        )
        .all()
    )

    matched = []
    for quest in active_quests:
        try:
            if check_quest_match(quest, entry, detected_skills, detected_activities):
                matched.append(quest)
        except Exception:
            logger.exception("Quest %s: error during match check", quest.id)

    return matched


def check_quest_match(
    quest: Quest,
    entry: "JournalEntry",
    detected_skills: list[str],
    detected_activities: list[str],
) -> bool:
    """Return True if *entry* contributes progress toward *quest*.

    Matching logic per completion_type:

    one_time
        Criteria (from template.parameters):
            keywords  — list of strings; at least one must appear in entry.content
            activity  — single string; must appear in detected_activities
        Both fields are optional; if absent the condition is treated as satisfied.
        Falls back to skill-name matching when no template criteria exist.

    cumulative
        Matches whenever the quest's linked skill appears in detected_skills.
        Progress quantity (e.g. word count) is handled by the caller.

    recursive
        Matches if the skill appears in detected_skills AND the current period
        hasn't been completed yet (current_progress < required_progress).
        Period resets are applied by an external scheduler, not this module.

    streak
        Matches if the skill appears in detected_skills AND the entry date
        differs from the date the quest was last updated (prevents double-
        counting the same day).

    Args:
        quest:               Quest to evaluate.
        entry:               Journal entry being processed.
        detected_skills:     Skill names from the AI pipeline.
        detected_activities: Activity phrases from the AI pipeline.

    Returns:
        True if the entry should advance this quest.
    """
    ct = quest.completion_type

    # ------------------------------------------------------------------
    # one_time — keyword + activity matching
    # ------------------------------------------------------------------
    if ct == "one_time":
        criteria, parse_ok = _get_criteria(quest)

        if not parse_ok:
            # Malformed criteria fail closed.
            return False

        if criteria is None:
            # No template criteria: fall back to skill presence
            return _skill_matches(quest, detected_skills)

        raw_keywords = criteria.get("keywords", [])
        keywords = [kw.strip().lower() for kw in raw_keywords if isinstance(kw, str) and kw.strip()]
        activity = criteria.get("activity", "")
        activity_norm = activity.strip().lower() if isinstance(activity, str) else ""
        content = getattr(entry, "content", "") or ""
        content_lower = content.lower()
        detected_activity_set = {
            a.strip().lower() for a in detected_activities if isinstance(a, str) and a.strip()
        }

        keyword_ok = (
            any(kw in content_lower for kw in keywords)
            if keywords
            else True  # no keyword constraint → satisfied
        )
        activity_ok = (
            activity_norm in detected_activity_set
            if activity_norm
            else True  # no activity constraint → satisfied
        )

        return keyword_ok and activity_ok

    # ------------------------------------------------------------------
    # cumulative — match whenever the skill appears
    # ------------------------------------------------------------------
    if ct == "cumulative":
        return _skill_matches(quest, detected_skills)

    # ------------------------------------------------------------------
    # recursive — skill present AND period not yet exhausted
    # ------------------------------------------------------------------
    if ct == "recursive":
        if not _skill_matches(quest, detected_skills):
            return False
        # current_progress resets each period externally; stop matching once
        # the period target has been reached.
        if quest.current_progress >= quest.required_progress:
            return False

        entry_day = _entry_date(entry)
        last_day = _quest_last_progress_date(quest)
        if entry_day is not None and last_day == entry_day:
            return False
        return True

    # ------------------------------------------------------------------
    # streak — skill present AND this day hasn't been credited yet
    # ------------------------------------------------------------------
    if ct == "streak":
        if not _skill_matches(quest, detected_skills):
            return False

        entry_date = _entry_date(entry)
        if entry_date is None:
            return False
        last_updated_date = _quest_last_progress_date(quest)

        # Refuse to credit the same calendar day twice
        if last_updated_date == entry_date:
            return False

        # Streak is broken if the last update was more than one day ago
        if last_updated_date is not None and quest.current_progress > 0:
            gap = (entry_date - last_updated_date).days
            if gap > 1:
                # Broken streak: mark failed and do not match
                _break_streak(quest)
                return False

        return True

    logger.warning("Quest %s: unknown completion_type %r", quest.id, ct)
    return False


def update_quest_progress(quest: Quest, progress_delta: float, db: Session) -> bool:
    """Add *progress_delta* to *quest* and complete it if the target is reached.

    current_progress and required_progress are Integer columns, so progress_delta
    is rounded to the nearest integer before being applied.

    Side effects when quest is completed:
        quest.status          → "completed"
        quest.completed_at    → UTC datetime
        quest.completed_at_utc_ms → epoch milliseconds (Section 10 v8)

    Args:
        quest:          Quest to update.
        progress_delta: Amount of progress to add (e.g. 1 for a streak/one_time
                        tick, word count for cumulative).
        db:             SQLAlchemy session — a flush is issued so that
                        updated_at is refreshed for streak dedup.

    Returns:
        True if this update caused the quest to complete.
    """
    if quest.status == "completed":
        db.flush()
        return False

    delta = int(round(progress_delta))
    if delta <= 0:
        logger.info("Quest %s: ignoring non-positive progress delta %s", quest.id, progress_delta)
        db.flush()
        return False

    quest.current_progress += delta
    completed = quest.current_progress >= quest.required_progress and quest.status != "completed"

    if completed:
        now = datetime.now(timezone.utc)
        quest.status = "completed"
        quest.completed_at = now
        quest.completed_at_utc_ms = int(now.timestamp() * 1000)

    # Flush so that updated_at is refreshed (used by streak day-dedup check)
    db.flush()

    return completed


# ---------------------------------------------------------------------------
# Internal mutation helpers
# ---------------------------------------------------------------------------

def _break_streak(quest: Quest) -> None:
    """Mark a streak quest as failed due to a missed day.

    Called from check_quest_match; the caller's session flush will persist it.
    """
    quest.status = "failed"
    logger.info(
        "Quest %s (%r): streak broken — marking failed", quest.id, quest.name
    )
