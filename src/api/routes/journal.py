"""
Journal entry API endpoints.

Handles submission (POST /api/journal/entries) and status/listing queries.
Processing is handed off to the AI pipeline as a background task; callers
receive an immediate acknowledgement with the assigned entry_id.

Session lifetime note
---------------------
FastAPI's ``Depends(get_db)`` session is closed the moment the response is
sent.  Background tasks that run after the response therefore create their
own ``SessionLocal()`` session — never reuse the request session in a task.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from src.ai.pipeline import JournalEntryPipeline
from src.core.journal_hierarchy import process_journal_entry_with_hierarchy
from src.db.models.journal_entry import JournalEntry
from src.db.models.user import User
from src.db.session import SessionLocal, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class JournalEntryCreate(BaseModel):
    """Request body for submitting a new journal entry."""

    user_id: str = Field(..., description="User UUID (users.id)")
    raw_text: str = Field(
        ...,
        min_length=2,  # hard lower-bound; word-count check is below
        max_length=100_000,
        description="Raw journal text (2–10 000 words)",
    )

    @field_validator("raw_text")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        words = v.split()
        if len(words) < 2:
            raise ValueError(
                f"Entry too short ({len(words)} words). Minimum 2 words required."
            )
        if len(words) > 10_000:
            raise ValueError(
                f"Entry too long ({len(words)} words). Maximum 10 000 words allowed."
            )
        return v


class JournalEntryResponse(BaseModel):
    """Immediate acknowledgement returned after submission."""

    entry_id: str
    status: str
    message: str


class JournalEntryStatus(BaseModel):
    """Processing status for a single entry."""

    model_config = ConfigDict(from_attributes=True)

    entry_id: str
    status: str  # pending | processing | completed | failed
    word_count: int
    created_at: datetime
    processed_at: Optional[datetime]
    processing_duration_ms: Optional[int]
    error_message: Optional[str]


class JournalEntryListItem(BaseModel):
    """Summary row returned by the list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    entry_id: str
    status: str
    word_count: int
    created_at: datetime
    processed_at: Optional[datetime]


class JournalProcessingResult(BaseModel):
    """Hierarchy-aware processing result returned by the direct process endpoint."""

    status: str
    entry_id: str

    # Discovery — skills that were LOCKED and are now DISCOVERED
    discoveries: List[Dict[str, Any]]
    # XP after hierarchy redirection and spillage: {source_skill_id: xp}
    xp_distributions: Dict[str, int]
    # Detailed XP application: {source_skill_id: {old_xp, new_xp, …}}
    xp_results: Dict[str, Dict[str, Any]]
    # UNLOCKED_HIDDEN skills activated by this entry
    activations: List[Dict[str, Any]]
    # State transitions triggered by parent(s) crossing Lv20
    unlocks: List[Dict[str, Any]]
    total_skills_affected: int


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _process_entry_background(entry_id: str, user_id: str) -> None:
    """
    Async background task — runs after the HTTP response is sent.

    Opens its own DB session (the request session is already closed) and
    drives the entry through the full 17-step AI pipeline.  Pipeline-internal
    errors are handled gracefully: the entry status is updated by the
    pipeline itself, and failures are persisted to the RecoveryQueue so they
    can be retried without data loss.
    """
    db: Session = SessionLocal()
    try:
        # Mark as processing so status queries reflect in-flight work.
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if entry is None:
            logger.error(
                "Background task could not find entry %s — aborting.", entry_id
            )
            return

        entry.status = "processing"
        db.commit()

        pipeline = JournalEntryPipeline(db_session=db)
        result = await pipeline.process_entry(entry_id, user_id)
        logger.info(
            "Entry %s processed (status=%s, degraded=%s).",
            entry_id,
            result.get("status"),
            result.get("meta", {}).get("degraded", False),
        )

    except Exception:
        # Pipeline already updates entry.status and writes to RecoveryQueue on
        # failure; we just log here so the background exception is visible.
        logger.exception("Unhandled error in background processing of entry %s.", entry_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _word_count(text: str) -> int:
    return len(text.split())


def _entry_to_status(entry: JournalEntry) -> JournalEntryStatus:
    return JournalEntryStatus(
        entry_id=entry.id,
        status=entry.status,
        word_count=_word_count(entry.content),
        created_at=entry.created_at,
        processed_at=entry.processed_at,
        processing_duration_ms=entry.processing_duration_ms,
        error_message=entry.error_message,
    )


def _entry_to_list_item(entry: JournalEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "status": entry.status,
        "word_count": _word_count(entry.content),
        "created_at": entry.created_at,
        "processed_at": entry.processed_at,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/entries",
    response_model=JournalEntryResponse,
    status_code=201,
    summary="Submit a journal entry for processing",
    responses={
        201: {"description": "Entry accepted — processing started in background"},
        404: {"description": "User not found"},
        422: {"description": "Validation error (word count, field constraints)"},
    },
)
async def submit_journal_entry(
    payload: JournalEntryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JournalEntryResponse:
    """
    Accept a raw journal entry and queue it for AI pipeline processing.

    The response is returned immediately with a ``submitted`` status.
    Actual processing (17-step AI pipeline) runs in a background task.
    Poll ``GET /api/journal/entries/{entry_id}`` to track progress.

    Idempotency
    -----------
    Each submission creates a new entry even if the text is identical.
    The pipeline itself is idempotent per ``(user_id, entry_id)`` pair:
    re-running the pipeline for the same entry replays the cached result.
    """
    # -- Verify user exists --------------------------------------------------
    user_exists = db.query(User.id).filter(User.id == payload.user_id).first()
    if user_exists is None:
        raise HTTPException(
            status_code=404,
            detail=f"User {payload.user_id!r} not found.",
        )

    # -- Persist entry in 'pending' state ------------------------------------
    entry_id = str(uuid.uuid4())
    entry = JournalEntry(
        id=entry_id,
        user_id=payload.user_id,
        content=payload.raw_text,
        entry_type="text",
        status="pending",
        question_state="none",
    )
    db.add(entry)
    db.commit()

    words = _word_count(payload.raw_text)
    logger.info(
        "Created journal entry %s for user %s (%d words).",
        entry_id,
        payload.user_id,
        words,
    )

    # -- Enqueue background processing ---------------------------------------
    background_tasks.add_task(_process_entry_background, entry_id, payload.user_id)

    return JournalEntryResponse(
        entry_id=entry_id,
        status="submitted",
        message="Entry submitted for processing.",
    )


@router.get(
    "/entries/{entry_id}",
    response_model=JournalEntryStatus,
    summary="Get processing status of a journal entry",
    responses={
        200: {"description": "Entry status"},
        404: {"description": "Entry not found"},
    },
)
def get_entry_status(
    entry_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID for tenant isolation")],
    db: Session = Depends(get_db),
) -> JournalEntryStatus:
    """
    Return the current processing status of a journal entry.

    ``user_id`` is required as a query param to enforce tenant isolation —
    an entry is only visible to its owning user.

    Status progression::

        pending → processing → completed
                              ↘ failed
    """
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == entry_id, JournalEntry.user_id == user_id)
        .first()
    )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entry {entry_id!r} not found.",
        )

    return _entry_to_status(entry)


@router.get(
    "/entries",
    summary="List journal entries for a user",
    responses={
        200: {"description": "Paginated list of journal entries"},
    },
)
def list_user_entries(
    user_id: Annotated[str, Query(description="User UUID")],
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max results")] = 20,
    status: Annotated[
        Optional[str],
        Query(
            description="Filter by status: pending | processing | completed | failed"
        ),
    ] = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    List journal entries for a user, ordered newest-first.

    Supports optional status filtering and cursor-style pagination via
    ``skip`` / ``limit``.  Maximum 100 results per page.
    """
    # Validate status value if provided
    valid_statuses = {"pending", "processing", "completed", "failed", "pending_other_type"}
    if status and status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status {status!r}. Must be one of: {sorted(valid_statuses)}.",
        )

    query = db.query(JournalEntry).filter(JournalEntry.user_id == user_id)

    if status:
        query = query.filter(JournalEntry.status == status)

    entries = (
        query.order_by(JournalEntry.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [_entry_to_list_item(e) for e in entries]


@router.post(
    "/entries/{entry_id}/process",
    response_model=JournalProcessingResult,
    summary="Directly process a completed entry through the skill hierarchy",
    responses={
        200: {"description": "Hierarchy processing results"},
        404: {"description": "Entry not found or not completed"},
        422: {"description": "skill_xp_awards missing or malformed"},
    },
)
def process_entry_with_hierarchy(
    entry_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    skill_xp_awards: Dict[str, int],
    db: Session = Depends(get_db),
) -> JournalProcessingResult:
    """
    Run hierarchy-aware XP distribution for a completed journal entry.

    Accepts a pre-computed ``{source_skill_id: base_xp}`` mapping and applies
    the full hierarchy pipeline: discovery → XP distribution (redirection +
    spillage) → activation → batch unlock evaluation.

    The pipeline background task invokes this logic automatically via step 14
    when ``user_id`` is provided.  This endpoint exists for manual triggering,
    testing, and replaying failed entries.

    ``source_skill_id`` values must match keys in the global skill hierarchy
    JSONL (e.g. ``"skill_professional_python"``).
    """
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == entry_id, JournalEntry.user_id == user_id)
        .first()
    )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entry {entry_id!r} not found.",
        )

    results = process_journal_entry_with_hierarchy(
        user_id=user_id,
        entry_id=entry_id,
        skill_xp_awards=skill_xp_awards,
        db=db,
    )

    logger.info(
        "Hierarchy processing for entry %s: %d skill(s) affected, "
        "%d discovery/unlock(s).",
        entry_id,
        results["total_skills_affected"],
        len(results["discoveries"]) + len(results["unlocks"]),
    )

    return JournalProcessingResult(
        status="processed",
        entry_id=entry_id,
        **results,
    )
