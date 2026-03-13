"""Anomaly detection orchestrator.

Integrates anomaly scoring into the journal processing pipeline.
Implements Section 9.7 (Reward Finalization Correctness).

Rules (Section 9.7):
- Reward finalization MUST NOT proceed without an anomaly score.
- If a score is missing  → compute synchronously inline.
- If computation fails   → raise (job must fail; no partial rewards).
- Atomicity: anomaly row + XP/coin writes share the same DB transaction
  (this module flushes only; the caller is responsible for commit).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.core.anomaly_scoring import AnomalyScoringService
from src.core.anomaly_similarity import SimilarityService
from src.core.anomaly_text_normalization import TextNormalizer
from src.db.models.anomaly import AnomalyScore
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured


class AnomalyOrchestrator:
    """Orchestrate full anomaly detection for journal pipeline entries."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.similarity_service = SimilarityService(db)
        self.scoring_service = AnomalyScoringService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_anomaly_score(
        self,
        user_id: str,
        entry_id: str,
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Return existing anomaly score or compute it synchronously (Section 9.7).

        Guarantees:
        - Returns a score dict on success.
        - Raises RuntimeError if computation fails (caller must abort the job).

        Returns:
            {
                "score": float,
                "troll_multiplier": Decimal,
                "detection_factors": dict,
                "calculated_at": datetime,
            }
        """
        now_utc = now_utc or datetime.now(timezone.utc)

        existing = (
            self.db.query(AnomalyScore)
            .filter(
                AnomalyScore.user_id == user_id,
                AnomalyScore.entry_id == entry_id,
            )
            .first()
        )
        if existing:
            return {
                "score": existing.score,
                "troll_multiplier": Decimal(str(existing.troll_multiplier)),
                "detection_factors": json.loads(existing.detection_factors),
                "calculated_at": existing.calculated_at,
            }

        # Missing — compute synchronously.  Any exception propagates as-is so
        # the pipeline step fails and the job is aborted (Section 9.7).
        try:
            return self.compute_anomaly_score(user_id, entry_id, now_utc)
        except Exception as exc:
            raise RuntimeError(
                f"Anomaly computation failed for entry {entry_id}: {exc}"
            ) from exc

    def compute_anomaly_score(
        self,
        user_id: str,
        entry_id: str,
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Run the full anomaly detection pipeline and persist the result.

        Steps:
        1. Load entry + structured data
        2. Normalize & tokenize
        3. Calculate similarity against causal window
        4. Detect markers
        5. Compute score
        6. Calculate troll multiplier
        7. Persist (idempotent flush)
        8. Return result dict

        Raises:
            ValueError: if the entry is not found or in an unprocessable state.
        """
        now_utc = now_utc or datetime.now(timezone.utc)

        # 1. Load entry ---------------------------------------------------
        entry = (
            self.db.query(JournalEntry)
            .filter(
                JournalEntry.id == entry_id,
                JournalEntry.user_id == user_id,
            )
            .first()
        )
        if entry is None:
            raise ValueError(f"Entry {entry_id} not found for user {user_id}")

        if entry.status not in ("processing", "completed"):
            raise ValueError(
                f"Entry {entry_id} has status {entry.status!r}; "
                "expected 'processing' or 'completed'"
            )

        # Structured row (may be None if Step 08 not yet run or degraded)
        structured = (
            self.db.query(JournalEntryStructured)
            .filter(JournalEntryStructured.entry_id == entry_id)
            .first()
        )
        task_type: str = (structured.task_type or "") if structured else ""
        unique_skill_ids: List[str] = _extract_skill_ids(structured)

        # 2. Normalize & tokenize -----------------------------------------
        tokens_all, tokens_sim, token_count = TextNormalizer.normalize_and_tokenize(
            entry.content
        )

        # Insufficient signal — score 0, multiplier 1.0 (Section 9.2)
        if token_count < 10:
            return self._short_entry_result(
                user_id=user_id,
                entry_id=entry_id,
                token_count=token_count,
                now_utc=now_utc,
            )

        # 3. Similarity against causal window (Section 9.3) ---------------
        (
            sim_max,
            sim_avg,
            most_similar_entry_id,
            most_similar_created_at_ms,
            most_similar_sim,
        ) = self.similarity_service.calculate_similarity_metrics(
            user_id=user_id,
            entry_id=entry_id,
            entry_created_at=entry.created_at,
            current_tokens_sim=tokens_sim,
        )

        # 4-6. Score + troll multiplier (Sections 9.5 + 9.6) -------------
        current_created_at_ms = int(entry.created_at.timestamp() * 1000)
        detection_factors = self.scoring_service.compute_anomaly_score(
            tokens_all=tokens_all,
            token_count=token_count,
            sim_max=sim_max,
            sim_avg=sim_avg,
            most_similar_entry_id=most_similar_entry_id,
            most_similar_created_at_ms=most_similar_created_at_ms,
            most_similar_sim=most_similar_sim,
            unique_skill_ids=unique_skill_ids,
            task_type=task_type,
            current_created_at_ms=current_created_at_ms,
        )

        score: float = detection_factors["score"]
        troll_multiplier = Decimal(str(detection_factors["troll_multiplier"]))

        # 7. Persist (idempotent, flush-only) -----------------------------
        self._persist_anomaly_score(
            user_id=user_id,
            entry_id=entry_id,
            score=score,
            troll_multiplier=troll_multiplier,
            detection_factors=detection_factors,
            now_utc=now_utc,
        )

        # 8. Return -------------------------------------------------------
        return {
            "score": score,
            "troll_multiplier": troll_multiplier,
            "detection_factors": detection_factors,
            "calculated_at": now_utc,
        }

    def persist_planned_result(
        self,
        *,
        user_id: str,
        entry_id: str,
        planned_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persist a precomputed anomaly result inside the caller's transaction."""
        calculated_at = planned_result.get("calculated_at")
        if not isinstance(calculated_at, datetime):
            calculated_at = datetime.now(timezone.utc)

        self._persist_anomaly_score(
            user_id=user_id,
            entry_id=entry_id,
            score=float(planned_result["score"]),
            troll_multiplier=Decimal(str(planned_result["troll_multiplier"])),
            detection_factors=dict(planned_result["detection_factors"]),
            now_utc=calculated_at,
        )
        return {
            "score": float(planned_result["score"]),
            "troll_multiplier": Decimal(str(planned_result["troll_multiplier"])),
            "detection_factors": dict(planned_result["detection_factors"]),
            "calculated_at": calculated_at,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _short_entry_result(
        self,
        user_id: str,
        entry_id: str,
        token_count: int,
        now_utc: datetime,
    ) -> Dict[str, Any]:
        """Return and persist a zero-score result for entries below the token threshold."""
        detection_factors: Dict[str, Any] = {
            "algorithm_version": "9.2.0",
            "stopwords_version": "stopwords_enfr_v1",
            "marker_set_version": "anomaly_markers_v1",
            "token_count": token_count,
            "recent_window_n": 0,
            "sim_max": 0.0,
            "sim_avg": 0.0,
            "most_similar_entry_id": None,
            "most_similar_created_at_ms": None,
            "most_similar_sim": None,
            "score_unclamped": 0.0,
            "score": 0.0,
            "troll_multiplier": 1.0,
            "components": [],
            "factors_truncated": False,
        }
        self._persist_anomaly_score(
            user_id=user_id,
            entry_id=entry_id,
            score=0.0,
            troll_multiplier=Decimal("1.0"),
            detection_factors=detection_factors,
            now_utc=now_utc,
        )
        return {
            "score": 0.0,
            "troll_multiplier": Decimal("1.0"),
            "detection_factors": detection_factors,
            "calculated_at": now_utc,
        }

    def _persist_anomaly_score(
        self,
        user_id: str,
        entry_id: str,
        score: float,
        troll_multiplier: Decimal,
        detection_factors: Dict[str, Any],
        now_utc: datetime,
    ) -> AnomalyScore:
        """Add AnomalyScore to the session (idempotent; flush-only).

        The caller is responsible for committing the enclosing transaction
        so that the anomaly row and XP awards are written atomically
        (Section 9.7).
        """
        existing = (
            self.db.query(AnomalyScore)
            .filter(
                AnomalyScore.user_id == user_id,
                AnomalyScore.entry_id == entry_id,
            )
            .first()
        )
        if existing:
            return existing

        row = AnomalyScore(
            user_id=user_id,
            entry_id=entry_id,
            score=score,
            troll_multiplier=float(troll_multiplier),
            detection_factors=json.dumps(
                detection_factors, separators=(",", ":"), ensure_ascii=False
            ),
            calculated_at=now_utc,
        )
        self.db.add(row)
        self.db.flush()
        return row


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _extract_skill_ids(structured: Optional[JournalEntryStructured]) -> List[str]:
    """Extract unique skill IDs from the structured entry's skills_themes_involved JSON."""
    if structured is None or not structured.skills_themes_involved:
        return []
    try:
        items = json.loads(structured.skills_themes_involved)
        return list({s.get("skill_id") for s in items if s.get("skill_id")})
    except Exception:
        return []
