"""Forgiveness preset definitions and display metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetParams:
    """Immutable parameter bundle for a forgiveness preset."""

    skill_decay_rate: float
    skill_grace_days: int
    insight_decay_rate: float
    insight_grace_days: int
    critical_threshold: float


DEFAULT_FORGIVENESS_PRESET = "balanced"


FORGIVENESS_PRESETS: dict[str, PresetParams] = {
    DEFAULT_FORGIVENESS_PRESET: PresetParams(
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
    # Adaptive uses the balanced baseline and applies an in-memory overlay.
    "adaptive": PresetParams(
        skill_decay_rate=0.05,
        skill_grace_days=7,
        insight_decay_rate=0.10,
        insight_grace_days=3,
        critical_threshold=0.80,
    ),
    # Custom keeps user-supplied values; this placeholder supports validation.
    "custom": PresetParams(
        skill_decay_rate=0.05,
        skill_grace_days=7,
        insight_decay_rate=0.10,
        insight_grace_days=3,
        critical_threshold=0.80,
    ),
}


FORGIVENESS_PRESET_NAMES: dict[str, str] = {
    DEFAULT_FORGIVENESS_PRESET: "Balanced",
    "hardcore": "Hardcore",
    "lenient": "Lenient",
    "zen": "Zen",
    "adaptive": "Adaptive",
    "custom": "Custom",
}


VALID_PRESETS: frozenset[str] = frozenset(FORGIVENESS_PRESETS)


def get_preset_params(preset: str) -> PresetParams:
    """Return canonical parameters for *preset*."""
    if preset not in FORGIVENESS_PRESETS:
        raise ValueError(
            f"Unknown forgiveness preset {preset!r}. "
            f"Valid presets: {sorted(VALID_PRESETS)}"
        )
    return FORGIVENESS_PRESETS[preset]


def get_preset_name(preset: str) -> str:
    """Return the display name for *preset*."""
    if preset not in FORGIVENESS_PRESET_NAMES:
        raise ValueError(
            f"Unknown forgiveness preset {preset!r}. "
            f"Valid presets: {sorted(VALID_PRESETS)}"
        )
    return FORGIVENESS_PRESET_NAMES[preset]
