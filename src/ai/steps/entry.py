"""Step 16 — Finalise journal entry processing state.

Marks the entry as ``completed``, records ``processed_at`` (UTC), and
computes ``processing_duration_ms`` from the pipeline run-start timestamp.
A ``db.flush()`` is issued so the state is visible within the current
transaction before the outer commit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def mark_completed(
    *,
    entry: Any,
    run_started: datetime,
    db: Session,
) -> dict[str, Any]:
    """Transition a journal entry to the ``completed`` status.

    Args:
        entry:       JournalEntry ORM object (must be attached to *db*).
        run_started: UTC datetime when the pipeline run began — used to
                     compute ``processing_duration_ms``.
        db:          SQLAlchemy session (write — issues a flush).

    Returns:
        Dict with keys:
            ``entry_status``           — "completed".
            ``processing_duration_ms`` — non-negative int.
    """
    entry.status = "completed"
    entry.processed_at = _now_utc()
    entry.processing_duration_ms = max(
        0,
        int((entry.processed_at - run_started).total_seconds() * 1000),
    )
    entry.error_message = None
    db.flush()
    return {
        "entry_status": entry.status,
        "processing_duration_ms": entry.processing_duration_ms,
    }
