"""Tests for realm preference defaults and rank wording presets."""

from src.core.realm import (
    RealmRankWordingPreset,
    default_user_preferences,
    get_rank_wording_mapping,
    list_rank_wording_presets,
    normalize_user_preferences,
)


def test_default_user_preferences_include_realm_scope_and_rank_wording() -> None:
    prefs = default_user_preferences()
    assert prefs["realm"]["scope"] == {
        "visual": True,
        "naming": False,
        "messages": False,
        "llm": False,
    }
    assert prefs["realm"]["ranks_wording"]["preset"] == "standard"


def test_rank_wording_mapping_standard_and_arcane() -> None:
    standard = get_rank_wording_mapping(RealmRankWordingPreset.STANDARD)
    arcane = get_rank_wording_mapping(RealmRankWordingPreset.ARCANE_MAGIC_SYSTEM)

    assert standard["F"] == "Beginner"
    assert standard["SSS"] == "Legend"
    assert arcane["F"] == "Novice"
    assert arcane["SSS"] == "Archon of Magic"


def test_normalize_user_preferences_fills_missing_fields() -> None:
    normalized = normalize_user_preferences(
        {"realm": {"scope": {"visual": False}, "ranks_wording": {"preset": "invalid"}}}
    )
    assert normalized["realm"]["scope"] == {
        "visual": False,
        "naming": False,
        "messages": False,
        "llm": False,
    }
    assert normalized["realm"]["ranks_wording"]["preset"] == "standard"


def test_list_rank_wording_presets_contains_all_expected_presets() -> None:
    presets = list_rank_wording_presets()
    preset_ids = {entry["preset"] for entry in presets}
    assert preset_ids == {
        "standard",
        "arcane_magic_system",
        "galactic_tech_rank",
        "divine_ascension_path",
        "cultivation_realm",
    }
