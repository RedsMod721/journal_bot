"""Anomaly detection API endpoints.

Read-only access to pre-computed anomaly scores.

Architecture references:
    §9.9.2  GET /anomaly/{entry_id}
    §9.9.4  GET /anomaly/recent
"""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.anomaly_orchestrator import AnomalyOrchestrator
from src.db.models.anomaly import AnomalyScore
from src.db.models.journal_entry import JournalEntry
from src.db.session import get_db

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AnomalyScoreResponse(BaseModel):
    entry_id: str
    score: float = Field(..., ge=0.0, le=10.0)
    troll_multiplier: float = Field(..., ge=1.0, le=5.0)
    calculated_at: Optional[str] = None
    missing: bool = False
    detection_factors: Optional[Dict[str, Any]] = None


class RecentAnomaliesResponse(BaseModel):
    anomalies: List[AnomalyScoreResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_response(anomaly: AnomalyScore) -> AnomalyScoreResponse:
    return AnomalyScoreResponse(
        entry_id=anomaly.entry_id,
        score=anomaly.score,
        troll_multiplier=float(anomaly.troll_multiplier),
        calculated_at=anomaly.calculated_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        missing=False,
        detection_factors=json.loads(anomaly.detection_factors),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/recent", response_model=RecentAnomaliesResponse)
def get_recent_anomalies(
    user_id: str = Query(..., description="User UUID"),
    min_score: float = Query(6.0, ge=0.0, le=10.0, description="Minimum anomaly score filter"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db),
) -> RecentAnomaliesResponse:
    """Get recent high-anomaly entries (Section 9.9.4).

    Results ordered by score DESC, calculated_at DESC, entry_id DESC.
    """
    rows = (
        db.query(AnomalyScore)
        .filter(
            AnomalyScore.user_id == user_id,
            AnomalyScore.score >= min_score,
        )
        .order_by(
            AnomalyScore.score.desc(),
            AnomalyScore.calculated_at.desc(),
            AnomalyScore.entry_id.desc(),
        )
        .limit(limit)
        .all()
    )

    anomalies = [_row_to_response(r) for r in rows]
    return RecentAnomaliesResponse(anomalies=anomalies, total=len(anomalies))


@router.get("/{entry_id}", response_model=AnomalyScoreResponse)
def get_anomaly_score(
    entry_id: str,
    user_id: str = Query(..., description="User UUID"),
    db: Session = Depends(get_db),
) -> AnomalyScoreResponse:
    """Get anomaly score for a single entry (Section 9.9.2).

    Returns the stored score when available. When no score has been computed
    yet, returns a default response with missing=true rather than 404 — the
    entry may simply not have been processed yet.

    Raises:
        404  — entry does not exist or does not belong to user_id.
        409  — entry exists but is not in 'completed' status.
    """
    entry = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.id == entry_id,
            JournalEntry.user_id == user_id,
        )
        .first()
    )

    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.status != "completed":
        raise HTTPException(status_code=409, detail="Entry not completed")

    anomaly = (
        db.query(AnomalyScore)
        .filter(
            AnomalyScore.user_id == user_id,
            AnomalyScore.entry_id == entry_id,
        )
        .first()
    )

    if anomaly is not None:
        return _row_to_response(anomaly)

    # Score not yet computed — return default with missing=true (Section 9.9.2)
    return AnomalyScoreResponse(
        entry_id=entry_id,
        score=0.0,
        troll_multiplier=1.0,
        calculated_at=None,
        missing=True,
        detection_factors=None,
    )


@router.post("/{entry_id}/compute", response_model=AnomalyScoreResponse)
def compute_anomaly_score(
    entry_id: str,
    user_id: str = Query(..., description="User UUID"),
    db: Session = Depends(get_db),
) -> AnomalyScoreResponse:
    """Compute and persist anomaly score explicitly when missing."""
    entry = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.id == entry_id,
            JournalEntry.user_id == user_id,
        )
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.status != "completed":
        raise HTTPException(status_code=409, detail="ENTRY_NOT_COMPLETED")

    existing = (
        db.query(AnomalyScore)
        .filter(
            AnomalyScore.user_id == user_id,
            AnomalyScore.entry_id == entry_id,
        )
        .first()
    )
    if existing is not None:
        return _row_to_response(existing)

    try:
        result = AnomalyOrchestrator(db).compute_anomaly_score(user_id, entry_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"ANOMALY_COMPUTE_FAILED: {exc}",
        ) from exc

    return AnomalyScoreResponse(
        entry_id=entry_id,
        score=result["score"],
        troll_multiplier=float(result["troll_multiplier"]),
        calculated_at=result["calculated_at"].astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        missing=False,
        detection_factors=result["detection_factors"],
    )
