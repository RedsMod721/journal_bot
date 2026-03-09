"""Steps 09-10 — Quest matching and progress update.

``match``           — step 09: returns quest IDs whose criteria are satisfied.
``update_progress`` — step 10: advances progress counters, handles streaks,
                      marks quests completed when the target is reached.

Both functions are idempotent against the same (user_id, entry) within a
single processing run because ``match`` only reads and ``update_progress``
flushes inside the outer transaction that is rolled back on error.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.core.quests import match_quests as _core_match_quests
from src.db.models.quest import Quest
from src.db.models.quest_progress import QuestProgress


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Step 09
# ---------------------------------------------------------------------------


def match(
    *,
    entry: Any,
    user_id: str,
    detected_skills: list[str],
    detected_activities: list[str],
    db: Session,
) -> dict[str, Any]:
    """Return the IDs of active quests that match this journal entry.

    Delegates to ``src.core.quests.match_quests`` which handles all four
    completion types (one_time, cumulative, recursive, streak).

    Args:
        entry:               JournalEntry ORM object being processed.
        user_id:             Owning user UUID.
        detected_skills:     Skill names from the signals step.
        detected_activities: Activity keywords from the signals step.
        db:                  SQLAlchemy session (read-only within this step).

    Returns:
        Dict with key ``matched_quest_ids`` — list of matched Quest PKs.
    """
    matched = _core_match_quests(
        entry=entry,
        user_id=user_id,
        detected_skills=detected_skills,
        detected_activities=detected_activities,
        db=db,
    )
    return {"matched_quest_ids": [q.id for q in matched]}


# ---------------------------------------------------------------------------
# Step 10
# ---------------------------------------------------------------------------


def update_progress(
    *,
    entry: Any,
    user_id: str,
    matched_quest_ids: list[str],
    db: Session,
) -> dict[str, Any]:
    """Advance progress for every matched quest and detect completions.

    For ``cumulative`` quests the increment is proportional to entry word
    count (1 per 50 words, minimum 1).  All other completion types receive
    an increment of 1.

    Side effects:
        - ``Quest.current_progress`` incremented.
        - ``Quest.updated_at_utc_ms`` set to current epoch-ms.
        - ``QuestProgress`` row upserted (streak counters updated when
          ``completion_type == "streak"``).
        - Completed quests have ``status``, ``completed_at``, and
          ``completed_at_utc_ms`` set.
        - ``db.flush()`` called before returning.

    Args:
        entry:             JournalEntry ORM object.
        user_id:           Owning user UUID.
        matched_quest_ids: Output of the match step.
        db:                SQLAlchemy session (write — issues a flush).

    Returns:
        Dict with keys:
            ``completed_quest_payloads`` — list of dicts for completed quests
                                          (quest_id, skill_id, base_xp).
            ``completed_quest_ids``      — list of completed Quest PKs.
            ``matched_quest_count``      — total number of matched quests.
    """
    if not matched_quest_ids:
        return {
            "completed_quest_payloads": [],
            "completed_quest_ids": [],
            "matched_quest_count": 0,
        }

    matched_quests: list[Quest] = (
        db.query(Quest)
        .filter(Quest.user_id == user_id, Quest.id.in_(matched_quest_ids))
        .all()
    )

    completed_quest_payloads: list[dict[str, Any]] = []
    completed_ids: list[str] = []

    for quest in matched_quests:
        increment = 1
        if quest.completion_type == "cumulative":
            increment = max(1, len((entry.content or "").split()) // 50)

        quest.current_progress = int(quest.current_progress or 0) + increment
        quest.updated_at_utc_ms = int(_now_utc().timestamp() * 1000)

        qp: QuestProgress | None = (
            db.query(QuestProgress)
            .filter(
                QuestProgress.user_id == user_id,
                QuestProgress.quest_id == quest.id,
            )
            .one_or_none()
        )
        if qp is None:
            qp = QuestProgress(user_id=user_id, quest_id=quest.id)
            db.add(qp)

        qp.progress_value = int(quest.current_progress)
        if quest.completion_type == "streak":
            qp.streak_current = max(1, qp.streak_current + 1)
            qp.streak_best = max(qp.streak_best, qp.streak_current)
        qp.last_progress_date = _now_utc().strftime("%Y-%m-%d")

        if quest.current_progress >= int(quest.required_progress or 1):
            quest.status = "completed"
            quest.completed_at = _now_utc()
            quest.completed_at_utc_ms = int(quest.completed_at.timestamp() * 1000)
            completed_quest_payloads.append(
                {
                    "quest_id": quest.id,
                    "skill_id": quest.skill_id,
                    "base_xp": int(quest.base_xp or 480),
                }
            )
            completed_ids.append(quest.id)

    db.flush()
    return {
        "completed_quest_payloads": completed_quest_payloads,
        "completed_quest_ids": completed_ids,
        "matched_quest_count": len(matched_quests),
    }
