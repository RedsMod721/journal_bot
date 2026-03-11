"""Forgiveness preset definitions — canonical source of truth.

Section 4.2.1 of the architecture spec defines six presets. The ``custom``
preset has no fixed parameters; users supply their own rates.

Usage::

    from src.core.forgiveness_presets import get_preset_params, FORGIVENESS_PRESETS

    params = get_preset_params("zen")
    # params.skill_decay_rate == 0.01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PresetParams:
    """Immutable parameter bundle for a forgiveness preset."""

    skill_decay_rate: float       # Staleness gained per 24 h (0.0–1.0)
    skill_grace_days: int         # Days before skill decay starts
    insight_decay_rate: float     # Strength lost per 24 h (0.0–1.0)
    insight_grace_days: int       # Days before insight decay starts
    critical_threshold: float     # Staleness fraction that triggers a critical flag (0.0–1.0)


# ---------------------------------------------------------------------------
# Canonical preset table
# ---------------------------------------------------------------------------
FORGIVENESS_PRESETS: Dict[str, PresetParams] = {
    "balanced": PresetParams(
        skill_decay_rate=0.05,
        skill_grace_days=7,
        insight_decay_rate=0.10,
        insight_grace_days=3,
        critical_threshold=0.80,
    ),
    "hardcore": PresetParams(
        skill_decay_rate=0.08,
        skill_grace_days=3,
        insight_decay_rate=0.15,
        insight_grace_days=1,
        critical_threshold=0.70,
    ),
    "lenient": PresetParams(
        skill_decay_rate=0.03,
        skill_grace_days=10,
        insight_decay_rate=0.07,
        insight_grace_days=5,
        critical_threshold=0.85,
    ),
    "zen": PresetParams(
        skill_decay_rate=0.01,
        skill_grace_days=14,
        insight_decay_rate=0.03,
        insight_grace_days=7,
        critical_threshold=0.90,
    ),
    # adaptive: base rates equal to balanced; actual rates are modified at
    # runtime based on the user's recent activity streak.
    "adaptive": PresetParams(
        skill_decay_rate=0.05,
        skill_grace_days=7,
        insight_decay_rate=0.10,
        insight_grace_days=3,
        critical_threshold=0.80,
    ),
    # custom: placeholder entry so membership tests work; callers that need
    # the user-supplied rates must read them from ForgivenessConfig directly.
    "custom": PresetParams(
        skill_decay_rate=0.05,
        skill_grace_days=7,
        insight_decay_rate=0.10,
        insight_grace_days=3,
        critical_threshold=0.80,
    ),
}

VALID_PRESETS: frozenset[str] = frozenset(FORGIVENESS_PRESETS)


def get_preset_params(preset: str) -> PresetParams:
    """Return the :class:`PresetParams` for *preset*.

    Raises :exc:`ValueError` for unknown preset names.
    """
    if preset not in FORGIVENESS_PRESETS:
        raise ValueError(
            f"Unknown forgiveness preset {preset!r}. "
            f"Valid presets: {sorted(VALID_PRESETS)}"
        )
    return FORGIVENESS_PRESETS[preset]
