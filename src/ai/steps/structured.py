"""Step 08 — Persist AI-extracted structured fields.

Upserts a ``JournalEntryStructured`` row for the given (user_id, entry_id)
pair.  Idempotent: if the row already exists it is updated in-place.
A ``db.flush()`` is issued so the new ``id`` is available to the caller
before the outer transaction commits.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.journal_entry import JournalEntryStructured


def run(
    *,
    user_id: str,
    entry_id: str,
    canonical_text: str,
    detection: dict[str, Any],
    resolved_skill_names: list[str] | None = None,
    db: Session,
) -> dict[str, Any]:
    """Upsert the structured representation of a journal entry.

    Args:
        user_id:        Owning user UUID.
        entry_id:       Journal entry UUID.
        canonical_text: Normalised entry text from the normalise step.
        detection:      Signal-detection output dict (step 07).
        resolved_skill_names:
            Canonical skill names resolved from activity routing, when available.
        db:             SQLAlchemy session (write — issues a flush).

    Returns:
        Dict with key ``structured_id`` — the PK of the upserted row.
    """
    row = (
        db.query(JournalEntryStructured)
        .filter(
            JournalEntryStructured.user_id == user_id,
            JournalEntryStructured.entry_id == entry_id,
        )
        .one_or_none()
    )
    if row is None:
        row = JournalEntryStructured(user_id=user_id, entry_id=entry_id)
        db.add(row)

    row.canonical_text = canonical_text
    row.primary_action_type = (
        detection["detected_activities"][0]
        if detection["detected_activities"]
        else None
    )
    row.goal_relation = None
    row.time_of_day_bucket = None
    row.dominant_emotions = json.dumps(detection["dominant_emotions"])
    row.energy_level = int(detection["energy_level"])
    row.self_compassion_score = int(detection["self_compassion_score"])
    row.task_type = detection["task_type"]
    row.success_quality = None
    row.blockers_or_obstacles = None
    row.support_used = None
    row.delay_from_planned_time_minutes = None
    row.reflection_depth = None
    skill_names = list(resolved_skill_names or detection["detected_skills"])
    row.skills_themes_involved = json.dumps(skill_names)
    row.categories = None
    row.sentiment_score = None
    row.safety_flags = None

    db.flush()
    return {"structured_id": row.id}
