"""
Anomaly detection scoring algorithm.

Implements Section 9.5 (Anomaly Score Model) and Section 9.6 (Troll Multiplier)
from COMPLETE_ARCHITECTURE.md.

CRITICAL: Follow exact formulas for cross-platform reproducibility.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Tuple

from src.core.anomaly_markers import MarkerDetector


class AnomalyScoringService:
    """Calculate anomaly score 0–10 and troll multiplier 1.0–5.0."""

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        """Clamp value to [min_val, max_val]."""
        return max(min_val, min(max_val, value))

    # ------------------------------------------------------------------
    # Section 9.5.2 — Positive components
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_novelty_points(sim_max: float) -> Tuple[float, float]:
        """Novelty points (Section 9.5.2).

        novelty_raw    = clamp(1.0 - sim_max, 0.0, 1.0)
        novelty_points = 3.0 * novelty_raw

        Returns: (novelty_points, novelty_raw)
        """
        novelty_raw = AnomalyScoringService.clamp(1.0 - sim_max, 0.0, 1.0)
        novelty_points = 3.0 * novelty_raw
        return novelty_points, novelty_raw

    @staticmethod
    def calculate_creativity_points(creativity_hits: int) -> Tuple[float, int]:
        """Creativity points (Section 9.5.3).

        creativity_points = min(2.0, 0.5 * creativity_hits)

        Returns: (creativity_points, creativity_hits)
        """
        points = min(2.0, 0.5 * creativity_hits)
        return points, creativity_hits

    @staticmethod
    def calculate_combo_points(
        unique_skill_count: int,
        has_combo_connector: bool,
        token_count: int,
    ) -> Tuple[float, int]:
        """Combo points (Section 9.5.3).

        If unique_skills >= 3: 2.0
        Elif unique_skills == 2: 1.0
        Elif has_combo_connector AND token_count >= 40: 1.0
        Else: 0.0

        Returns: (combo_points, unique_skill_count)
        """
        if unique_skill_count >= 3:
            return 2.0, unique_skill_count
        if unique_skill_count == 2:
            return 1.0, unique_skill_count
        if has_combo_connector and token_count >= 40:
            return 1.0, unique_skill_count
        return 0.0, unique_skill_count

    @staticmethod
    def calculate_automation_points(automation_hits: int) -> Tuple[float, int]:
        """Automation points (Section 9.5.3).

        1.5 if any automation marker, else 0.0.

        Returns: (automation_points, automation_hits)
        """
        points = 1.5 if automation_hits > 0 else 0.0
        return points, automation_hits

    @staticmethod
    def calculate_constraint_points(constraint_hits: int) -> Tuple[float, int]:
        """Constraint points (Section 9.5.3).

        1.5 if any constraint marker, else 0.0.

        Returns: (constraint_points, constraint_hits)
        """
        points = 1.5 if constraint_hits > 0 else 0.0
        return points, constraint_hits

    @staticmethod
    def calculate_structured_creative_bonus(task_type: str) -> Tuple[float, str]:
        """Structured creative bonus (Section 9.5.3).

        0.5 if task_type (normalized) == 'creative', else 0.0.

        Returns: (bonus_points, normalized_task_type)
        """
        normalized = (task_type or "").strip().lower()
        bonus = 0.5 if normalized == "creative" else 0.0
        return bonus, normalized

    # ------------------------------------------------------------------
    # Section 9.5.2 — Penalties
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_repetition_penalty(sim_max: float) -> Tuple[float, float]:
        """Repetition penalty (Section 9.5.2).

        Ramps from 0 at sim_max=0.80 to 4.0 at sim_max>=1.00:
            repetition_penalty = 4.0 * clamp((sim_max - 0.80) / 0.20, 0.0, 1.0)

        Returns: (repetition_penalty, sim_max)
        """
        if sim_max <= 0.80:
            return 0.0, sim_max
        raw = AnomalyScoringService.clamp((sim_max - 0.80) / 0.20, 0.0, 1.0)
        return 4.0 * raw, sim_max

    @staticmethod
    def calculate_farming_penalty(
        has_farming: bool,
        sim_max: float,
        most_similar_created_at_ms: Optional[int],
        current_created_at_ms: int,
    ) -> Tuple[float, int]:
        """Farming penalty (Section 9.5.2).

        Base penalty: 2.0 if any farming marker detected.
        Burst add-on: +2.0 if sim_max >= 0.95 AND most-similar entry is within 6 hours.

        Returns: (farming_penalty, raw_marker_flag)  — raw is 1 if farming, else 0.
        """
        if not has_farming:
            return 0.0, 0

        penalty = 2.0

        if sim_max >= 0.95 and most_similar_created_at_ms is not None:
            time_delta_ms = current_created_at_ms - most_similar_created_at_ms
            six_hours_ms = 6 * 60 * 60 * 1000
            if time_delta_ms <= six_hours_ms:
                penalty += 2.0  # burst add-on

        return penalty, 1

    @staticmethod
    def calculate_boilerplate_penalty(token_count: int) -> Tuple[float, int]:
        """Boilerplate penalty (Section 9.5.3).

        If token_count < 20:
            boilerplate_penalty = 1.5 * clamp((20 - token_count) / 20, 0.0, 1.0)
        Else: 0.0

        Returns: (boilerplate_penalty, token_count)
        """
        if token_count >= 20:
            return 0.0, token_count
        raw = AnomalyScoringService.clamp((20 - token_count) / 20, 0.0, 1.0)
        return 1.5 * raw, token_count

    # ------------------------------------------------------------------
    # Section 9.6 — Troll multiplier (EXACT formula, Decimal precision)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_troll_multiplier(score: float) -> Decimal:
        """Troll multiplier (Section 9.6).

        Formula: m = 1.0 + ((a / 10.0) ** 1.5) * 4.0

        CRITICAL implementation details:
          - Use Decimal throughout for cross-platform reproducibility.
          - Compute x^1.5 as x * sqrt(x), NOT float pow, to avoid drift.
          - Quantize to 6 decimal places with ROUND_HALF_UP.

        Returns: Decimal in [1.000000, 5.000000]
        """
        x = Decimal(str(score)) / Decimal("10.0")

        # x^1.5 = x * sqrt(x)  — avoids cross-language floating-point drift
        x_sqrt = x.sqrt()
        x_1_5 = x * x_sqrt

        multiplier = Decimal("1.0") + (x_1_5 * Decimal("4.0"))

        return multiplier.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Section 9.5.1 — Master compute method
    # ------------------------------------------------------------------

    @staticmethod
    def compute_anomaly_score(
        tokens_all: List[str],
        token_count: int,
        sim_max: float,
        sim_avg: float,
        most_similar_entry_id: Optional[str],
        most_similar_created_at_ms: Optional[int],
        most_similar_sim: Optional[float],
        unique_skill_ids: List[str],
        task_type: str,
        current_created_at_ms: int,
    ) -> Dict[str, Any]:
        """Compute the complete anomaly score for an entry (Section 9.5.1).

        All marker detection happens here from tokens_all; the caller does NOT
        need to pre-detect markers.

        Returns:
            detection_factors dict ready for JSON storage (Section 9.8.2).
        """
        # --- Marker detection -------------------------------------------
        farming_hits = MarkerDetector.detect_farming(tokens_all)
        has_farming = farming_hits > 0

        creativity_hits = MarkerDetector.detect_creativity(tokens_all)
        automation_hits = MarkerDetector.detect_automation(tokens_all, has_farming)
        constraint_hits = MarkerDetector.detect_constraint(tokens_all)
        combo_connector_hits = MarkerDetector.detect_combo_connectors(tokens_all)

        # --- Positive components ----------------------------------------
        novelty_points, novelty_raw = AnomalyScoringService.calculate_novelty_points(sim_max)
        creativity_points, _ = AnomalyScoringService.calculate_creativity_points(creativity_hits)
        combo_points, _ = AnomalyScoringService.calculate_combo_points(
            len(unique_skill_ids),
            combo_connector_hits > 0,
            token_count,
        )
        automation_points, _ = AnomalyScoringService.calculate_automation_points(automation_hits)
        constraint_points, _ = AnomalyScoringService.calculate_constraint_points(constraint_hits)
        structured_bonus, _ = AnomalyScoringService.calculate_structured_creative_bonus(task_type)

        # --- Penalties --------------------------------------------------
        repetition_penalty, _ = AnomalyScoringService.calculate_repetition_penalty(sim_max)
        boilerplate_penalty, _ = AnomalyScoringService.calculate_boilerplate_penalty(token_count)
        farming_penalty, _ = AnomalyScoringService.calculate_farming_penalty(
            has_farming,
            sim_max,
            most_similar_created_at_ms,
            current_created_at_ms,
        )

        # --- Final score (Section 9.5.1) --------------------------------
        score_unclamped = (
            novelty_points
            + creativity_points
            + combo_points
            + automation_points
            + constraint_points
            + structured_bonus
            - repetition_penalty
            - boilerplate_penalty
            - farming_penalty
        )
        score = AnomalyScoringService.clamp(score_unclamped, 0.0, 10.0)

        # --- Troll multiplier -------------------------------------------
        troll_multiplier = AnomalyScoringService.calculate_troll_multiplier(score)

        # --- detection_factors payload (Section 9.8.2) ------------------
        detection_factors: Dict[str, Any] = {
            "algorithm_version": "9.2.0",
            "stopwords_version": "stopwords_enfr_v1",
            "marker_set_version": "anomaly_markers_v1",
            "token_count": token_count,
            "recent_window_n": 20,
            "sim_max": round(sim_max, 4),
            "sim_avg": round(sim_avg, 4),
            "most_similar_entry_id": most_similar_entry_id,
            "most_similar_created_at_ms": most_similar_created_at_ms,
            "most_similar_sim": round(most_similar_sim, 4) if most_similar_sim is not None else None,
            "score_unclamped": round(score_unclamped, 4),
            "score": round(score, 4),
            "troll_multiplier": float(troll_multiplier),
            "components": [
                {
                    "key": "novelty_points",
                    "points": round(novelty_points, 4),
                    "raw": round(novelty_raw, 4),
                },
                {
                    "key": "creativity_points",
                    "points": round(creativity_points, 4),
                    "raw": creativity_hits,
                },
                {
                    "key": "combo_points",
                    "points": round(combo_points, 4),
                    "raw": len(unique_skill_ids),
                },
                {
                    "key": "automation_points",
                    "points": round(automation_points, 4),
                    "raw": automation_hits,
                },
                {
                    "key": "constraint_points",
                    "points": round(constraint_points, 4),
                    "raw": constraint_hits,
                },
                {
                    "key": "structured_creative_bonus",
                    "points": round(structured_bonus, 4),
                    "raw": None,
                },
                {
                    "key": "repetition_penalty",
                    "points": round(repetition_penalty, 4),
                    "raw": round(sim_max, 4),
                },
                {
                    "key": "boilerplate_penalty",
                    "points": round(boilerplate_penalty, 4),
                    "raw": token_count,
                },
                {
                    "key": "farming_penalty",
                    "points": round(farming_penalty, 4),
                    "raw": farming_hits,
                },
            ],
            "factors_truncated": False,
        }

        return detection_factors
