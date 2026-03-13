"""
Personality selection algorithm.

Implements Section 3.3 (Selection Logic) from COMPLETE_ARCHITECTURE.md.
CRITICAL: Deterministic, safety-first selection.

Priority order:
    0. Safety override  → therapist (always wins)
    1. Forced contexts  → observer/raphael/wargod/coach
    2. User override    → pass hard gates or deny
    3. Cooldown gate    → keep current if within window
    4. Weighted select  → 0.7 * context_weight + 0.3 * likability_weight
    5. Fallback         → observer
"""

import hashlib
import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.db.models.personality import PersonalityState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical personality IDs (Section 3.0.2)
CANONICAL_PERSONALITIES: List[str] = [
    "observer",
    "therapist",
    "coach",
    "sassy",
    "wargod",
    "raphael",
]
SELECTOR_VERSION = 1

# Mapping: personality → PersonalityState column name
PERSONALITY_LIKABILITY_COLUMN: Dict[str, str] = {
    "observer": "likability_observer",
    "therapist": "likability_therapist",
    "coach": "likability_coach",
    "sassy": "likability_sassy",
    "wargod": "likability_wargod",
    "raphael": "likability_raphael",
}

# Hard-gate thresholds (Section 3.3.5)
_SASSY_HARMONY_MIN = 40       # below this → sassy disabled
_WARGOD_HARMONY_MIN = 50      # below this → wargod disabled
_SASSY_LIKABILITY_MIN = 0.30  # below this → sassy disabled


# ---------------------------------------------------------------------------
# PersonalitySelector
# ---------------------------------------------------------------------------


class PersonalitySelector:
    """
    Deterministic, priority-ordered personality selector.

    Instantiate once per request with the active DB session, then call
    ``select_personality()``.  The selector never commits; callers are
    responsible for committing after they have persisted selection results.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _seed_for_entry(
        user_id: str,
        entry_id: str,
        pipeline_version: str = "v3.0",
    ) -> int:
        """
        Deterministic 64-bit seed (Section 3.3.5).

        seed = int( SHA256(user_id:entry_id:pipeline_version)[:16], 16 )

        Same (user_id, entry_id, pipeline_version) always produces the same
        seed, making weighted selection reproducible across retries.
        """
        material = f"{user_id}:{entry_id}:{pipeline_version}".encode("utf-8")
        digest = hashlib.sha256(material).hexdigest()
        return int(digest[:16], 16)

    @staticmethod
    def _dedupe_preserve_order(items: List[str]) -> List[str]:
        """Remove duplicates while preserving first-occurrence order."""
        seen: set = set()
        result: List[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @staticmethod
    def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
        """
        Clamp weights to ≥ 0, fill missing personalities with 0, then
        normalise to a probability distribution that sums to 1.0.

        Returns all-zeros dict if the total is 0 (caller falls back to
        observer).
        """
        clamped: Dict[str, float] = {}
        total = 0.0
        for pid in CANONICAL_PERSONALITIES:
            v = max(0.0, float(weights.get(pid, 0.0)))
            clamped[pid] = v
            total += v

        if total <= 0.0:
            return {pid: 0.0 for pid in CANONICAL_PERSONALITIES}

        return {pid: clamped[pid] / total for pid in CANONICAL_PERSONALITIES}

    @staticmethod
    def _hard_gate_reasons(
        pid: str,
        harmony: int,
        likability: Dict[str, float],
        wargod_used_today: bool,
        wargod_eligible: bool,
    ) -> List[str]:
        """
        Return canonical gate_id strings that block *pid* (Section 3.3.5).

        An empty list means the personality passes all gates.
        """
        reasons: List[str] = []

        if pid == "sassy":
            if harmony < _SASSY_HARMONY_MIN:
                reasons.append("gate_harmony_lt_40_disable_sassy")
            if likability.get("sassy", 0.5) < _SASSY_LIKABILITY_MIN:
                reasons.append("gate_likability_sassy_lt_30_disable_sassy")

        if pid == "wargod":
            if harmony < _WARGOD_HARMONY_MIN:
                reasons.append("gate_harmony_lt_50_disable_wargod")
            if wargod_used_today:
                reasons.append("gate_wargod_daily_cap")
            if not wargod_eligible:
                reasons.append("gate_wargod_not_eligible")

        return reasons

    # ------------------------------------------------------------------
    # Context-weight calculation (Section 3.3.6)
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_context_weights(
        user_state: Dict[str, Any],
        entry_text: str,
        anomaly_score: float,
        harmony: int,
    ) -> Dict[str, float]:
        """
        Heuristic context weights for each personality (Section 3.3.6).

        These additive weights are combined with likability weights before
        normalisation.  They intentionally sum to > 1.0 in many branches;
        ``_normalize_weights`` handles normalisation.
        """
        weights: Dict[str, float] = {}

        # Observer — neutral / tutorial baseline
        weights["observer"] = 0.30
        if user_state.get("tutorial_active"):
            weights["observer"] += 0.50

        # Therapist — mental-health support
        weights["therapist"] = 0.20
        if harmony < 60:
            weights["therapist"] += 0.30
        if int(user_state.get("overwork_stage", 0)) >= 2:
            weights["therapist"] += 0.30

        # Coach — achievement focus
        weights["coach"] = 0.20
        if user_state.get("major_achievement"):
            weights["coach"] += 0.50
        if 70 <= harmony <= 90:
            weights["coach"] += 0.20

        # Sassy — playful, high-harmony contexts
        weights["sassy"] = 0.15
        if harmony > 70:
            weights["sassy"] += 0.30

        # Wargod — epic celebration
        weights["wargod"] = 0.05
        if user_state.get("major_achievement") and anomaly_score > 6.0:
            weights["wargod"] += 0.60
        if float(user_state.get("anomaly_contribution", 0.0)) > 2.0:
            weights["wargod"] += 0.30

        # Raphael — philosophical / regression arcs
        weights["raphael"] = 0.10
        if user_state.get("regression_arc_active"):
            weights["raphael"] += 0.70

        return weights

    # ------------------------------------------------------------------
    # Main selection entry point
    # ------------------------------------------------------------------

    def select_personality(
        self,
        user_id: str,
        entry_id: str,
        entry_text: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        now_utc: datetime,
        requested_personality: Optional[str] = None,
        pipeline_version: str = "v3.0",
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Select the personality that should generate content for this entry.

        Parameters
        ----------
        user_id:
            UUID of the user.
        entry_id:
            UUID of the journal entry being processed.
        entry_text:
            Raw entry content (used for context-weight heuristics).
        user_state:
            Snapshot of relevant user metrics::

                {
                    "harmony_score": int,          # 0-100
                    "anomaly_score": float,         # e.g. 0-10
                    "anomaly_contribution": float,  # contribution delta
                    "tutorial_active": bool,
                    "regression_arc_active": bool,
                    "major_achievement": bool,
                    "overwork_stage": int,          # 0-3
                }

        safety_result:
            Output from the safety/crisis detection step::

                {"force_therapist": bool, "risk_level": str, ...}

        now_utc:
            Authoritative UTC timestamp for this pipeline run.
        requested_personality:
            Optional user-requested personality (may be denied by gates).
        pipeline_version:
            Pinned version string used in deterministic seeding.

        Returns
        -------
        (selected, reason, factors)
            selected  — one of CANONICAL_PERSONALITIES
            reason    — human-readable selection path
            factors   — dict of all decision inputs for audit logging
        """
        # ------------------------------------------------------------------
        # 0. Load (or create) personality state
        # ------------------------------------------------------------------
        personality_state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        if not personality_state:
            personality_state = PersonalityState(user_id=user_id)
            self.db.add(personality_state)
            self.db.flush()  # get defaults without committing

        gates_applied: List[str] = []
        active_before: str = personality_state.active_personality or "observer"

        # ------------------------------------------------------------------
        # 1. Extract user-state scalars
        # ------------------------------------------------------------------
        harmony = int(user_state.get("harmony_score", 100))
        anomaly_score = float(user_state.get("anomaly_score", 0.0))
        anomaly_contribution = float(user_state.get("anomaly_contribution", 0.0))
        major_achievement = bool(user_state.get("major_achievement", False))

        # Wargod eligibility (Section 3.3.6):
        #   eligible if anomaly_contribution > 2.0  OR
        #              (major_achievement AND anomaly_score > 6.0)
        wargod_eligible = (anomaly_contribution > 2.0) or (
            major_achievement and anomaly_score > 6.0
        )

        # ------------------------------------------------------------------
        # 2. Wargod daily cap — parse last_selection_factors
        # ------------------------------------------------------------------
        wargod_used_today = False
        try:
            last_factors: Dict[str, Any] = json.loads(
                personality_state.last_selection_factors or "{}"
            )
            last_used_date: Optional[str] = last_factors.get("wargod_last_used_date_utc")
            if last_used_date:
                wargod_used_today = last_used_date == now_utc.date().isoformat()
        except Exception:
            pass  # corrupt JSON → treat as not used

        # ------------------------------------------------------------------
        # 3. Validate requested_personality (drop if invalid)
        # ------------------------------------------------------------------
        override_meta: Dict[str, Any] = {}
        if requested_personality is not None:
            override_meta["requested_personality"] = str(requested_personality)
            override_meta["override_applied"] = False
            gates_applied.append("gate_user_override_requested")

            if requested_personality not in CANONICAL_PERSONALITIES:
                override_meta["override_denied_reason"] = "invalid_personality"
                gates_applied.append("gate_user_override_denied_invalid")
                requested_personality = None  # discard unknown name

        # ------------------------------------------------------------------
        # Convenience: build base factors dict (filled once, mutated per path)
        # ------------------------------------------------------------------
        def _base_factors(**extra: Any) -> Dict[str, Any]:
            return {
                "active_personality_before": active_before,
                "cooldown_seconds_remaining": 0,
                "wargod_used_today": wargod_used_today,
                "harmony_score": harmony,
                "anomaly_score": anomaly_score,
                "gates_applied": self._dedupe_preserve_order(gates_applied),
                **override_meta,
                **extra,
            }

        # ------------------------------------------------------------------
        # PRIORITY 0: SAFETY OVERRIDE
        # ------------------------------------------------------------------
        if safety_result.get("force_therapist", False):
            if requested_personality is not None:
                override_meta["override_denied_reason"] = "safety_override"
                gates_applied.append("gate_user_override_denied_safety")
            gates_applied.append("gate_safety_force_therapist")
            return "therapist", "safety_override", _base_factors()

        # ------------------------------------------------------------------
        # PRIORITY 1: FORCED CONTEXTS
        # ------------------------------------------------------------------
        def _deny_override_forced() -> None:
            """Mark override as denied due to forced context."""
            if requested_personality is not None:
                override_meta["override_denied_reason"] = "forced_context"
                gates_applied.append("gate_user_override_denied_forced_context")

        if user_state.get("tutorial_active", False):
            _deny_override_forced()
            return (
                "observer",
                "forced_context",
                _base_factors(forced_context_type="tutorial"),
            )

        if user_state.get("regression_arc_active", False):
            _deny_override_forced()
            return (
                "raphael",
                "forced_context",
                _base_factors(forced_context_type="regression_arc"),
            )

        if major_achievement and anomaly_score > 6.0:
            _deny_override_forced()
            # Prefer wargod if gates allow; fall back to coach
            if harmony >= _WARGOD_HARMONY_MIN and not wargod_used_today:
                return (
                    "wargod",
                    "forced_context",
                    _base_factors(forced_context_type="major_achievement"),
                )
            return (
                "coach",
                "forced_context",
                _base_factors(forced_context_type="major_achievement"),
            )

        # ------------------------------------------------------------------
        # Prepare likability weights (used by gates and weighted selection)
        # ------------------------------------------------------------------
        likability: Dict[str, float] = {}
        for pid, col in PERSONALITY_LIKABILITY_COLUMN.items():
            raw: int = getattr(personality_state, col, 50)
            likability[pid] = max(0, min(100, int(raw))) / 100.0

        # ------------------------------------------------------------------
        # PRIORITY 2: USER OVERRIDE (with hard-gate enforcement)
        # ------------------------------------------------------------------
        if requested_personality is not None:
            hard_gates = self._hard_gate_reasons(
                requested_personality,
                harmony=harmony,
                likability=likability,
                wargod_used_today=wargod_used_today,
                wargod_eligible=wargod_eligible,
            )
            if hard_gates:
                gates_applied.extend(hard_gates)
                override_meta["override_denied_reason"] = "hard_gate"
                gates_applied.append("gate_user_override_denied_hard_gate")
                # Fall through to cooldown / weighted selection
            else:
                override_meta["override_applied"] = True
                return str(requested_personality), "user_override", _base_factors()

        # ------------------------------------------------------------------
        # PRIORITY 3: COOLDOWN GATE (sticky personality)
        # ------------------------------------------------------------------
        cooldown: int = int(personality_state.switch_cooldown_seconds or 600)
        cooldown_remaining = 0

        if cooldown > 0 and personality_state.last_switched_at is not None:
            try:
                last_dt = personality_state.last_switched_at
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed = (now_utc - last_dt).total_seconds()

                if elapsed < cooldown:
                    cooldown_remaining = int(cooldown - elapsed)
                    # Only sticky if current personality still passes hard gates
                    current_gates = self._hard_gate_reasons(
                        active_before,
                        harmony=harmony,
                        likability=likability,
                        wargod_used_today=wargod_used_today,
                        wargod_eligible=wargod_eligible,
                    )
                    if not current_gates:
                        gates_applied.append("gate_cooldown_sticky")
                        return (
                            active_before,
                            "cooldown_gate",
                            _base_factors(cooldown_seconds_remaining=cooldown_remaining),
                        )
                    else:
                        gates_applied.append("gate_cooldown_bypassed_by_hard_gate")
            except Exception:
                pass  # malformed datetime → skip cooldown

        # ------------------------------------------------------------------
        # PRIORITY 4: WEIGHTED SELECTION
        # ------------------------------------------------------------------
        context_weights = self._calculate_context_weights(
            user_state, entry_text, anomaly_score, harmony
        )
        normalized_context = self._normalize_weights(context_weights)

        # Combine 0.7 * context + 0.3 * likability; zero out gate-blocked ones
        combined_weights: Dict[str, float] = {}
        for pid in CANONICAL_PERSONALITIES:
            pid_gates = self._hard_gate_reasons(
                pid,
                harmony=harmony,
                likability=likability,
                wargod_used_today=wargod_used_today,
                wargod_eligible=wargod_eligible,
            )
            if pid_gates:
                combined_weights[pid] = 0.0
                gates_applied.extend(pid_gates)
            else:
                ctx_w = context_weights.get(pid, 0.0)
                lik_w = likability.get(pid, 0.5)
                combined_weights[pid] = 0.7 * ctx_w + 0.3 * lik_w

        normalized = self._normalize_weights(combined_weights)

        # Deterministic random draw (same seed → same result on retries)
        seed = self._seed_for_entry(user_id, entry_id, pipeline_version)
        rng = random.Random(seed)  # isolated RNG — does not touch global state

        personalities = list(normalized.keys())
        probabilities = [normalized[p] for p in personalities]

        if sum(probabilities) > 0.0:
            selected: str = rng.choices(personalities, weights=probabilities, k=1)[0]
            selection_reason = "likability_weighted"
        else:
            selected = "observer"
            selection_reason = "fallback_observer"

        return (
            selected,
            selection_reason,
            _base_factors(
                cooldown_seconds_remaining=cooldown_remaining,
                weights_context=normalized_context,
                weights_context_raw=context_weights,
                weights_likability=likability,
                weights_final=normalized,
                seed=f"{user_id}:{entry_id}:{pipeline_version}",
            ),
        )
