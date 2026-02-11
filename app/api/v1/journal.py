"""
Journal entry API endpoints for Status Window.

Provides endpoints for creating, retrieving, and managing journal entries.
Journal entries are the primary input mechanism for the gamification system.
"""
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.events import get_event_bus
from app.crud.journal import create_journal_entry, get_journal_entry, get_user_journal_entries
from app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryWithProcessingResponse,
    ProcessingSummary,
    QuestProgressSummary,
)
from app.utils.database import get_db
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post(
    "/entry",
    response_model=JournalEntryWithProcessingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new journal entry",
    description="Create a new journal entry and process it through the gamification pipeline.",
)
async def create_entry(
    request: Request,
    entry_data: JournalEntryCreate,
    db: Session = Depends(get_db),
) -> JournalEntryWithProcessingResponse:
    """
    Create a new journal entry and process it.

    This endpoint:
    1. Creates the journal entry in the database
    2. Emits a "journal_entry.created" event
    3. Processes the entry through the orchestrator (XP, quests, titles)
    4. Returns the entry with a processing summary

    Args:
        request: FastAPI request (for accessing app state)
        entry_data: Journal entry creation data
        db: Database session

    Returns:
        JournalEntryWithProcessingResponse with entry and processing summary
    """
    start_time = time.perf_counter()

    # Create the journal entry
    entry = create_journal_entry(db, entry_data)
    logger.info("Journal entry created", entry_id=entry.id, user_id=entry.user_id)

    # Emit journal_entry.created event
    event_bus = get_event_bus()
    event_bus.emit(
        "journal_entry.created",
        {
            "user_id": entry.user_id,
            "entry_id": entry.id,
            "content": entry.content,
            "entry_type": entry.entry_type,
        },
    )

    # Process entry through orchestrator
    orchestrator = request.app.state.orchestrator
    try:
        result = orchestrator.process_entry(db, entry)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.error(
            "Journal entry processing failed unexpectedly",
            entry_id=entry.id,
            user_id=entry.user_id,
            error=str(exc),
            exc_info=True,
        )
        result = {
            "entry_id": entry.id,
            "status": "failed",
            "error": str(exc),
        }

    # Build processing summary
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)

    # Format XP distribution summary
    xp_distributed: dict[str, float] = {}
    xp_summary = result.get("xp_summary", {})
    distributions = xp_summary.get("distributions")
    if not distributions:
        distributions = xp_summary.get("awards", [])

    for dist in distributions:
        target_type = dist.get("target_type", dist.get("type", "unknown"))
        target_name = dist.get("target_name", dist.get("name", "unknown"))
        amount = dist.get("amount", dist.get("xp", 0))
        xp_distributed[f"{target_type}:{target_name}"] = amount

    # Format quest updates
    quests_updated = [
        QuestProgressSummary(
            quest_id=q["quest_id"],
            progress=q.get("progress", 0),
            completed=q.get("status") == "completed",
        )
        for q in result.get("quests_updated", [])
    ]

    # Format titles unlocked
    titles_unlocked = [t.get("title_name", "") for t in result.get("titles_awarded", [])]

    processing_summary = ProcessingSummary(
        xp_distributed=xp_distributed,
        quests_updated=quests_updated,
        titles_unlocked=titles_unlocked,
        total_processing_time_ms=processing_time_ms,
    )

    # Refresh entry to get updated state
    db.refresh(entry)

    return JournalEntryWithProcessingResponse(
        entry=JournalEntryResponse.model_validate(entry),
        processing_summary=processing_summary,
    )


@router.get(
    "/entry/{entry_id}",
    response_model=JournalEntryResponse,
    summary="Get a journal entry by ID",
)
async def get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
) -> JournalEntryResponse:
    """
    Retrieve a journal entry by its ID.

    Args:
        entry_id: UUID of the journal entry
        db: Database session

    Returns:
        JournalEntryResponse with entry data

    Raises:
        HTTPException 404: If entry not found
    """
    entry = get_journal_entry(db, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry {entry_id} not found",
        )
    return JournalEntryResponse.model_validate(entry)


@router.get(
    "/entries/{user_id}",
    response_model=list[JournalEntryResponse],
    summary="Get journal entries for a user",
)
async def get_entries_for_user(
    user_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[JournalEntryResponse]:
    """
    Retrieve journal entries for a user with pagination.

    Args:
        user_id: UUID of the user
        skip: Number of entries to skip (default 0)
        limit: Maximum entries to return (default 50)
        db: Database session

    Returns:
        List of JournalEntryResponse ordered by created_at descending
    """
    entries = get_user_journal_entries(db, user_id, skip=skip, limit=limit)
    return [JournalEntryResponse.model_validate(e) for e in entries]
