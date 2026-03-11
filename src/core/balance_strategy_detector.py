"""Balance system strategy detection service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.ai.steps.strategy import (
    STRATEGY_KEYS,
    _is_daily_grind,
    _is_harmony_balance,
    _is_mundane_focus,
    _is_social_risk,
    _is_study_burst,
    _is_troll_exploits,
)
from src.db.models.anomaly import AnomalyScore
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured


class StrategyDetector:
    """Detect up to two canonical balance strategies for an entry."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def detect_strategies(
        self,
        *,
        user_id: str,
        entry_id: str,
        entry: JournalEntry,
        structured: JournalEntryStructured | None,
    ) -> list[str]:
        canonical_text: str = (
            structured.canonical_text
            if structured and structured.canonical_text
            else entry.content
        )
        task_type: str | None = structured.task_type if structured else None
        energy_level: int | None = structured.energy_level if structured else None
        goal_relation: str | None = structured.goal_relation if structured else None
        skills_themes_involved: str | None = (
            structured.skills_themes_involved if structured else None
        )

        anomaly_score: float = self._fetch_anomaly_score(user_id, entry_id)

        raw_scores: dict[str, bool] = {
            "social": _is_social_risk(user_id, canonical_text, goal_relation, self.db),
            "study": _is_study_burst(
                user_id,
                entry_id,
                entry.created_at,
                canonical_text,
                task_type,
                self.db,
            ),
            "mundane": _is_mundane_focus(canonical_text, task_type, energy_level),
            "troll": _is_troll_exploits(anomaly_score),
            "grind": _is_daily_grind(user_id, entry.created_at, self.db),
            "harmony": _is_harmony_balance(
                user_id,
                self.db,
                task_type=task_type,
                content=canonical_text,
                skills_themes_involved=skills_themes_involved,
            ),
        }

        return [key for key in STRATEGY_KEYS if raw_scores.get(key)][:2]

    def _fetch_anomaly_score(self, user_id: str, entry_id: str) -> float:
        row = (
            self.db.query(AnomalyScore)
            .filter(
                AnomalyScore.user_id == user_id,
                AnomalyScore.entry_id == entry_id,
            )
            .one_or_none()
        )
        return float(row.score) if row is not None else 0.0
