"""Harmony dimension scoring and overwork detection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta, timezone
from typing import Dict

from sqlalchemy.orm import Session

from src.core.forgiveness_config_service import ForgivenessConfigService
from src.core.harmony_classifier import HarmonyClassifier, THEME_TO_DIM
from src.db.models.harmony import HarmonyDimension
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.skill import Theme
from src.db.models.xp import XpAward

OVERWORK_WARNING_THRESHOLD_PRODUCTIVITY = 0.85
OVERWORK_WARNING_THRESHOLD_REST = 0.35
OVERWORK_STAGE_2_THRESHOLD_PRODUCTIVITY = 0.90
OVERWORK_STAGE_2_THRESHOLD_REST = 0.25
OVERWORK_STAGE_2_LOW_REST = 0.30
OVERWORK_STAGE_3_THRESHOLD_PRODUCTIVITY = 0.95
OVERWORK_STAGE_3_THRESHOLD_REST = 0.20

_DIMS = ("physical", "mental", "social", "productivity", "rest", "growth", "creative")
_NEUTRAL_SCORES: Dict[str, float] = {d: 0.5 for d in _DIMS}
_DIMENSION_THRESHOLDS: Dict[str, int] = {
    "physical": 3,
    "mental": 4,
    "social": 3,
    "productivity": 5,
    "rest": 7,
    "growth": 2,
    "creative": 2,
}
_OVERWORK_DAY_THRESHOLDS = {
    "hardcore": (1, 2, 3),
    "balanced": (2, 4, 6),
    "lenient": (3, 6, 9),
    "zen": (4, 8, 12),
    "adaptive": (2, 4, 6),
    "custom": (2, 4, 6),
}


@dataclass(frozen=True)
class HarmonyWindowMetrics:
    dimension_scores: Dict[str, float]
    average_energy: float | None


@dataclass(frozen=True)
class OverworkStatus:
    stage: int
    consecutive_days: int
    condition: bool
    recommended_stage: int


class HarmonyScoringService:
    """Service for calculating harmony scores and overwork state."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.classifier = HarmonyClassifier(db)
        self.config_service = ForgivenessConfigService(db)

    def calculate_window_metrics(
        self,
        user_id: str,
        window_start_utc: datetime,
        window_end_utc: datetime,
    ) -> HarmonyWindowMetrics:
        entries = (
            self.db.query(JournalEntry, JournalEntryStructured)
            .outerjoin(
                JournalEntryStructured,
                (JournalEntryStructured.user_id == JournalEntry.user_id)
                & (JournalEntryStructured.entry_id == JournalEntry.id),
            )
            .filter(
                JournalEntry.user_id == user_id,
                JournalEntry.status == "completed",
                JournalEntry.created_at >= window_start_utc,
                JournalEntry.created_at < window_end_utc,
            )
            .all()
        )

        if not entries:
            return HarmonyWindowMetrics(dict(_NEUTRAL_SCORES), None)

        window_entry_ids = {entry.id for entry, _ in entries}
        dim_entry_ids: Dict[str, set[str]] = {d: set() for d in _DIMS}
        energy_values: list[int] = []

        for entry, structured in entries:
            if structured is None:
                continue

            if structured.energy_level is not None and 1 <= int(structured.energy_level) <= 10:
                energy_values.append(int(structured.energy_level))

            for dim in self.classifier.classify_dimensions(entry, structured):
                if dim in dim_entry_ids:
                    dim_entry_ids[dim].add(entry.id)

        theme_entry_ids = self._theme_hybrid_entry_ids(user_id, window_entry_ids)

        dimension_scores = {
            dim: self._score_dimension(
                activity_entry_count=len(dim_entry_ids[dim]),
                theme_entry_count=len(theme_entry_ids[dim]),
                threshold=_DIMENSION_THRESHOLDS[dim],
            )
            for dim in _DIMS
        }
        average_energy = (
            sum(energy_values) / len(energy_values) if energy_values else None
        )
        return HarmonyWindowMetrics(dimension_scores, average_energy)

    def calculate_overall_balance(self, dimension_scores: Dict[str, float]) -> float:
        values = [float(dimension_scores[d]) for d in _DIMS]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std_dev = variance ** 0.5
        return max(0.0, min(1.0, mean - (0.5 * std_dev)))

    @staticmethod
    def round_half_up(value: float, places: int = 5) -> float:
        quant = "1." + ("0" * places)
        return float(Decimal(str(value)).quantize(Decimal(quant), rounding=ROUND_HALF_UP))

    @staticmethod
    def _score_dimension(
        *,
        activity_entry_count: int,
        theme_entry_count: int,
        threshold: int,
    ) -> float:
        activity_score = min(1.0, activity_entry_count / threshold)
        theme_score = min(1.0, theme_entry_count / threshold)
        return max(activity_score, theme_score)

    def _theme_hybrid_entry_ids(
        self,
        user_id: str,
        window_entry_ids: set[str],
    ) -> Dict[str, set[str]]:
        theme_entry_ids: Dict[str, set[str]] = {dim: set() for dim in _DIMS}
        if not window_entry_ids:
            return theme_entry_ids

        rows = (
            self.db.query(XpAward.entry_id, Theme.name)
            .join(
                Theme,
                (Theme.user_id == XpAward.user_id) & (Theme.id == XpAward.theme_id),
            )
            .filter(
                XpAward.user_id == user_id,
                XpAward.distribution_type == "theme",
                XpAward.entry_id.in_(window_entry_ids),
            )
            .distinct()
            .all()
        )
        for entry_id, theme_name in rows:
            dim = THEME_TO_DIM.get((theme_name or "").strip().casefold())
            if dim:
                theme_entry_ids[dim].add(entry_id)
        return theme_entry_ids

    def get_read_only_overwork_status(
        self,
        harmony: HarmonyDimension,
        *,
        average_energy: float | None,
        preset: str,
    ) -> OverworkStatus:
        condition, recommended_stage = self._instant_overwork_status(
            productivity=harmony.productivity,
            rest=harmony.rest,
            physical=harmony.physical,
            average_energy=average_energy,
        )

        if not condition:
            return OverworkStatus(
                stage=harmony.overwork_stage,
                consecutive_days=harmony.overwork_consecutive_days,
                condition=False,
                recommended_stage=0,
            )

        persistence_stage = self._stage_from_consecutive_days(
            harmony.overwork_consecutive_days,
            preset,
        )
        return OverworkStatus(
            stage=min(recommended_stage, persistence_stage),
            consecutive_days=harmony.overwork_consecutive_days,
            condition=True,
            recommended_stage=recommended_stage,
        )

    def advance_overwork_state(
        self,
        harmony: HarmonyDimension,
        *,
        user_id: str,
        today_local: date,
        now_utc: datetime,
        average_energy: float | None,
    ) -> OverworkStatus:
        if harmony.overwork_last_evaluated_local_date == today_local:
            preset = self.config_service.get_or_create_config(user_id).preset
            return self.get_read_only_overwork_status(
                harmony,
                average_energy=average_energy,
                preset=preset,
            )

        preset = self.config_service.get_or_create_config(user_id).preset
        condition, recommended_stage = self._instant_overwork_status(
            productivity=harmony.productivity,
            rest=harmony.rest,
            physical=harmony.physical,
            average_energy=average_energy,
        )

        prior_stage = harmony.overwork_stage
        if condition:
            harmony.overwork_consecutive_days += 1
        else:
            harmony.overwork_consecutive_days = max(
                0,
                harmony.overwork_consecutive_days - 1,
            )

        persistence_stage = self._stage_from_consecutive_days(
            harmony.overwork_consecutive_days,
            preset,
        )
        if condition:
            new_stage = min(recommended_stage, persistence_stage)
        else:
            new_stage = max(0, prior_stage - 1)
            if harmony.overwork_consecutive_days == 0:
                new_stage = 0

        harmony.overwork_stage = new_stage
        harmony.overwork_last_evaluated_local_date = today_local
        if prior_stage != new_stage:
            harmony.overwork_last_changed_at_utc = now_utc

        self.db.flush()
        return OverworkStatus(
            stage=new_stage,
            consecutive_days=harmony.overwork_consecutive_days,
            condition=condition,
            recommended_stage=recommended_stage,
        )

    def _instant_overwork_status(
        self,
        *,
        productivity: float,
        rest: float,
        physical: float,
        average_energy: float | None,
    ) -> tuple[bool, int]:
        prod_high = productivity >= OVERWORK_WARNING_THRESHOLD_PRODUCTIVITY
        rest_low = rest <= OVERWORK_WARNING_THRESHOLD_REST
        energy_low = average_energy is not None and average_energy <= 4.0
        overwork_condition = prod_high and rest_low
        if not overwork_condition:
            return False, 0

        stage = 1
        if (
            (productivity >= OVERWORK_STAGE_2_THRESHOLD_PRODUCTIVITY and rest <= OVERWORK_STAGE_2_THRESHOLD_REST)
            or (
                productivity >= OVERWORK_WARNING_THRESHOLD_PRODUCTIVITY
                and rest <= OVERWORK_STAGE_2_LOW_REST
                and energy_low
            )
        ):
            stage = 2

        if (
            (productivity >= OVERWORK_STAGE_3_THRESHOLD_PRODUCTIVITY and rest <= OVERWORK_STAGE_3_THRESHOLD_REST)
            or (
                stage >= 2
                and physical <= 0.20
                and productivity >= OVERWORK_STAGE_2_THRESHOLD_PRODUCTIVITY
                and rest <= OVERWORK_STAGE_2_THRESHOLD_REST
            )
            or (
                energy_low
                and rest <= OVERWORK_STAGE_2_THRESHOLD_REST
                and productivity >= OVERWORK_STAGE_2_THRESHOLD_PRODUCTIVITY
            )
        ):
            stage = 3

        return True, stage

    @staticmethod
    def _stage_from_consecutive_days(consecutive_days: int, preset: str) -> int:
        stage_1, stage_2, stage_3 = _OVERWORK_DAY_THRESHOLDS.get(
            preset,
            _OVERWORK_DAY_THRESHOLDS["balanced"],
        )
        if consecutive_days >= stage_3:
            return 3
        if consecutive_days >= stage_2:
            return 2
        if consecutive_days >= stage_1:
            return 1
        return 0
