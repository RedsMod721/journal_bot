"""Realm preference primitives for user-facing naming/visual customization."""

from __future__ import annotations

from enum import Enum
from typing import Any

from src.core.enums import SkillRank


class RealmRankWordingPreset(str, Enum):
    """Supported rank-wording packs that can be selected per user."""

    STANDARD = "standard"
    ARCANE_MAGIC_SYSTEM = "arcane_magic_system"
    GALACTIC_TECH_RANK = "galactic_tech_rank"
    DIVINE_ASCENSION_PATH = "divine_ascension_path"
    CULTIVATION_REALM = "cultivation_realm"


REALM_RANK_WORDING_PRESET_NAMES: dict[RealmRankWordingPreset, str] = {
    RealmRankWordingPreset.STANDARD: "Standard",
    RealmRankWordingPreset.ARCANE_MAGIC_SYSTEM: "Arcane Magic System",
    RealmRankWordingPreset.GALACTIC_TECH_RANK: "Galactic Tech Rank",
    RealmRankWordingPreset.DIVINE_ASCENSION_PATH: "Divine Ascension Path",
    RealmRankWordingPreset.CULTIVATION_REALM: "Cultivation Realm",
}

_RANK_ORDER: tuple[SkillRank, ...] = tuple(SkillRank)

_REALM_RANK_WORDING_LABELS: dict[RealmRankWordingPreset, tuple[str, ...]] = {
    RealmRankWordingPreset.STANDARD: (
        "Beginner",
        "Amateur",
        "Apprentice",
        "Intermediate",
        "Advanced",
        "Expert",
        "Master",
        "Grandmaster",
        "Legend",
    ),
    RealmRankWordingPreset.ARCANE_MAGIC_SYSTEM: (
        "Novice",
        "Acolyte",
        "Mage",
        "Warlock",
        "Sorcerer",
        "Archmage",
        "Elder Mage",
        "High Sorcerer",
        "Archon of Magic",
    ),
    RealmRankWordingPreset.GALACTIC_TECH_RANK: (
        "Trainee",
        "Operative",
        "Engineer",
        "Cybernet",
        "Vanguard",
        "Apex Agent",
        "Neural Commander",
        "Quantum Overmind",
        "Singularity Entity",
    ),
    RealmRankWordingPreset.DIVINE_ASCENSION_PATH: (
        "Mortal",
        "Chosen",
        "Saint",
        "Prophet",
        "Demigod",
        "Seraph",
        "Archon",
        "Primordial",
        "Omnipresence",
    ),
    RealmRankWordingPreset.CULTIVATION_REALM: (
        "Body Tempering",
        "Qi Gathering",
        "Foundation Building",
        "Core Formation",
        "Nascent Soul",
        "Immortal Ascension",
        "Celestial Being",
        "Void Sovereign",
        "Tao Embodiment",
    ),
}

REALM_SCOPE_DEFAULTS: dict[str, bool] = {
    "visual": True,
    "naming": False,
    "messages": False,
    "llm": False,
}


def _resolve_preset(value: Any) -> RealmRankWordingPreset:
    if isinstance(value, RealmRankWordingPreset):
        return value
    if isinstance(value, str):
        try:
            return RealmRankWordingPreset(value)
        except ValueError:
            return RealmRankWordingPreset.STANDARD
    return RealmRankWordingPreset.STANDARD


def get_rank_wording_mapping(
    preset: RealmRankWordingPreset | str = RealmRankWordingPreset.STANDARD,
) -> dict[str, str]:
    """Return label mapping for one rank-wording preset keyed by base rank."""
    resolved = _resolve_preset(preset)
    labels = _REALM_RANK_WORDING_LABELS[resolved]
    return {
        rank.value: labels[index]
        for index, rank in enumerate(_RANK_ORDER)
    }


def list_rank_wording_presets() -> list[dict[str, Any]]:
    """Return all available rank-wording presets in API-friendly shape."""
    output: list[dict[str, Any]] = []
    for preset in RealmRankWordingPreset:
        mapping = get_rank_wording_mapping(preset)
        output.append(
            {
                "preset": preset.value,
                "name": REALM_RANK_WORDING_PRESET_NAMES[preset],
                "ranks": [
                    {"rank": rank.value, "wording": mapping[rank.value]}
                    for rank in _RANK_ORDER
                ],
            }
        )
    return output


def default_realm_preferences() -> dict[str, Any]:
    """Default realm preference block stored under user_preferences.realm."""
    return {
        "scope": dict(REALM_SCOPE_DEFAULTS),
        "ranks_wording": {"preset": RealmRankWordingPreset.STANDARD.value},
    }


def default_user_preferences() -> dict[str, Any]:
    """Default top-level user preferences payload."""
    return {"realm": default_realm_preferences()}


def normalize_realm_preferences(raw: Any) -> dict[str, Any]:
    """Normalize realm preferences to the canonical stored shape."""
    data = raw if isinstance(raw, dict) else {}

    raw_scope = data.get("scope")
    scope_payload = raw_scope if isinstance(raw_scope, dict) else {}
    scope = {
        key: (
            scope_payload[key]
            if isinstance(scope_payload.get(key), bool)
            else default_value
        )
        for key, default_value in REALM_SCOPE_DEFAULTS.items()
    }

    raw_wording = data.get("ranks_wording")
    wording_payload = raw_wording if isinstance(raw_wording, dict) else {}
    preset = _resolve_preset(wording_payload.get("preset"))

    return {
        "scope": scope,
        "ranks_wording": {"preset": preset.value},
    }


def normalize_user_preferences(raw: Any) -> dict[str, Any]:
    """Normalize top-level user preferences and inject defaults."""
    data = raw if isinstance(raw, dict) else {}
    return {
        "realm": normalize_realm_preferences(data.get("realm")),
    }
