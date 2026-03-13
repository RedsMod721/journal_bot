"""
Anomaly detection similarity calculation.

Implements Section 9.3 (Causal Similarity Window) from architecture.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Set, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from src.core.anomaly_text_normalization import TextNormalizer
from src.db.models.journal_entry import JournalEntry


class SimilarityService:
    """Calculate text similarity using 3-token shingles."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Core primitives
    # ------------------------------------------------------------------

    @staticmethod
    def shingles_3(tokens: List[str]) -> Set[Tuple[str, str, str]]:
        """Generate 3-token shingles.

        Section 9.0.5: Return empty set if len(tokens) < 3.
        """
        if len(tokens) < 3:
            return set()

        return {
            (tokens[i], tokens[i + 1], tokens[i + 2])
            for i in range(len(tokens) - 2)
        }

    @staticmethod
    def jaccard(set_a: Set, set_b: Set) -> float:
        """Calculate Jaccard similarity.

        Section 9.0.5:
        - If A is empty OR B is empty: return 0.0
        - Else: |A ∩ B| / |A ∪ B|
        """
        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    # ------------------------------------------------------------------
    # Causal window
    # ------------------------------------------------------------------

    def get_causal_window(
        self,
        user_id: str,
        entry_id: str,
        created_at: datetime,
    ) -> List[JournalEntry]:
        """Get causal similarity window (Section 9.3).

        Rules:
        - Only PRIOR completed entries
        - created_at < current, OR (created_at == current AND id < current id)
        - Within last 6 hours (21,600,000 ms)
        - Maximum 20 entries
        """
        window_start_dt = datetime.fromtimestamp(
            created_at.timestamp() - 6 * 60 * 60
        )

        # Entries strictly before the current timestamp
        prior_entries: List[JournalEntry] = (
            self.db.query(JournalEntry)
            .filter(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == "completed",
                    JournalEntry.created_at >= window_start_dt,
                    JournalEntry.created_at < created_at,
                )
            )
            .order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc())
            .limit(20)
            .all()
        )

        # Same-timestamp entries with a lexicographically smaller id
        same_time_entries: List[JournalEntry] = (
            self.db.query(JournalEntry)
            .filter(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == "completed",
                    JournalEntry.created_at == created_at,
                    JournalEntry.id < entry_id,
                )
            )
            .all()
        )

        # Merge, deduplicate, re-sort, cap at 20
        seen: Set[str] = set()
        unique: List[JournalEntry] = []
        for entry in prior_entries + same_time_entries:
            if entry.id not in seen:
                seen.add(entry.id)
                unique.append(entry)

        unique.sort(key=lambda e: (e.created_at, e.id), reverse=True)
        return unique[:20]

    # ------------------------------------------------------------------
    # Similarity metrics
    # ------------------------------------------------------------------

    def calculate_similarity_metrics(
        self,
        user_id: str,
        entry_id: str,
        entry_created_at: datetime,
        current_tokens_sim: List[str],
    ) -> Tuple[float, float, Optional[str], Optional[int], Optional[float]]:
        """Calculate similarity metrics for the current entry.

        Returns:
            (sim_max, sim_avg, most_similar_entry_id,
             most_similar_created_at_ms, most_similar_sim)
        """
        prior_entries = self.get_causal_window(user_id, entry_id, entry_created_at)

        if not prior_entries:
            return 0.0, 0.0, None, None, None

        current_shingles = self.shingles_3(current_tokens_sim)

        similarities = []
        for prior in prior_entries:
            _, prior_tokens_sim, _ = TextNormalizer.normalize_and_tokenize(prior.content)
            prior_shingles = self.shingles_3(prior_tokens_sim)
            sim = self.jaccard(current_shingles, prior_shingles)
            similarities.append(
                {
                    "entry_id": prior.id,
                    "created_at_ms": int(prior.created_at.timestamp() * 1000),
                    "similarity": sim,
                }
            )

        sim_values = [s["similarity"] for s in similarities]
        sim_max = max(sim_values)
        sim_avg = sum(sim_values) / len(sim_values)

        # Tie-break: highest similarity → latest created_at_ms → largest entry_id
        most_similar = max(
            similarities,
            key=lambda s: (s["similarity"], s["created_at_ms"], s["entry_id"]),
        )

        return (
            sim_max,
            sim_avg,
            most_similar["entry_id"],
            most_similar["created_at_ms"],
            most_similar["similarity"],
        )
