"""Unit tests for src.core.xp."""

import math
import pytest

from src.core.xp import (
    apportion_by_bp,
    build_skill_award_identity_key,
    build_theme_award_identity_key,
    calculate_level_from_xp,
    calculate_session_xp,
    calculate_xp_for_level,
    canonical_json_bytes,
    choose_primary_recipient_id,
    derive_theme_awards_from_skill_award,
    finalize_quest_xp,
    float_multiplier_to_bp,
    round_half_up,
    sort_xp_awards_for_payload,
)


def test_appendix_a1_reference_values() -> None:
    assert calculate_xp_for_level(0) == 0
    assert calculate_xp_for_level(-5) == 0
    assert calculate_xp_for_level(1) == 0
    assert calculate_xp_for_level(2) == 141
    assert calculate_xp_for_level(5) == 1359
    assert calculate_xp_for_level(30) == 102669
    assert calculate_xp_for_level(50) == 362365
    assert calculate_xp_for_level(100) == 5565727


def test_level_from_xp_supports_levels_above_100() -> None:
    xp_100 = calculate_xp_for_level(100)
    xp_101 = calculate_xp_for_level(101)
    assert calculate_level_from_xp(xp_100) == 100
    assert calculate_level_from_xp(xp_101) == 101
    assert calculate_level_from_xp(xp_101 - 1) == 100
    assert calculate_level_from_xp(0) == 1
    assert calculate_level_from_xp(-100) == 1


def test_calculate_xp_for_level_cache_extension_reuse_path() -> None:
    # First call extends the internal cumulative table beyond 100.
    high = calculate_xp_for_level(180)
    # Second call with a smaller (but still >100) level hits the "already extended" branch.
    mid = calculate_xp_for_level(140)
    assert high > mid > calculate_xp_for_level(100)


def test_finalize_quest_xp_uses_canonical_ordering() -> None:
    result = finalize_quest_xp(
        quest_xp_total=480,
        troll_bp=24142,
        variety_multiplier_bp=14800,
        arc_reward_multiplier_bp=20000,
        penalty_xp=0,
    )
    assert result["t1_after_troll"] == 1158
    assert result["t2_after_variety"] == 1713
    assert result["t3_after_arc"] == 3426
    assert result["final_xp"] == 3426


def test_round_half_up_and_bp_conversion() -> None:
    assert round_half_up(0.5) == 1
    assert round_half_up(1.5) == 2
    assert round_half_up(2.49) == 2
    assert float_multiplier_to_bp(1.2345) == 12345


def test_session_xp_compatibility_wrapper_uses_canonical_pipeline() -> None:
    result = calculate_session_xp(480, 60, 1.2, 0.30, 1.0)
    assert result == {"skill_xp": 1497, "theme_xp": 1}


def test_session_xp_rejects_non_canonical_minutes() -> None:
    with pytest.raises(ValueError):
        calculate_session_xp(480, 45, 1.0, 0.0, 1.0)


def test_apportion_by_bp_is_sum_preserving_with_tie_break() -> None:
    allocations = apportion_by_bp(695, [("cardio", 7000), ("python", 3000)])
    assert allocations == {"cardio": 487, "python": 208}
    assert sum(allocations.values()) == 695


def test_choose_primary_recipient_uses_max_then_lexicographic() -> None:
    recipients = [("b_skill", 5000), ("a_skill", 5000), ("c_skill", 3000)]
    assert choose_primary_recipient_id(recipients) == "a_skill"


def test_derive_theme_awards_from_skill_award() -> None:
    rows = derive_theme_awards_from_skill_award(
        source_skill_xp=317,
        source_skill_id="skill_a",
        theme_weights_bp=[("theme_c", 7000), ("theme_d", 3000)],
    )
    assert rows == [
        {
            "distribution_type": "theme",
            "theme_id": "theme_c",
            "source_skill_id": "skill_a",
            "source_skill_xp": 317,
            "amount": 222,
        },
        {
            "distribution_type": "theme",
            "theme_id": "theme_d",
            "source_skill_id": "skill_a",
            "source_skill_xp": 317,
            "amount": 95,
        },
    ]


def test_skill_award_identity_key_matches_architecture_vector() -> None:
    got = build_skill_award_identity_key(
        user_id="u1",
        entry_id="e1",
        quest_id="q1",
        xp_reason="quest_complete",
        distribution_type="primary",
        skill_id="s1",
        ruleset_version="r2026.02",
    )
    assert got == "f240862f3aec8490744342a57172af6926389e1f720975e207d9316e59a147d9"


def test_theme_award_identity_key_matches_architecture_vector_with_nulls() -> None:
    got = build_theme_award_identity_key(
        user_id="u1",
        entry_id="e1",
        quest_id="q1",
        xp_reason="quest_complete",
        distribution_type="theme",
        theme_id="t_focus",
        source_skill_id=None,
        source_skill_xp=None,
        ruleset_version="r2026.02",
    )
    assert got == "1f1280061922ad20184cdb52cca46f151e2fd1879927c820d8feb08b2707774e"


def test_theme_award_identity_key_non_null_source_fields() -> None:
    got = build_theme_award_identity_key(
        user_id="u2",
        entry_id="e2",
        quest_id="q2",
        xp_reason="quest_instant_complete",
        distribution_type="theme",
        theme_id="t_focus",
        source_skill_id="s2",
        source_skill_xp=317,
        ruleset_version="r2026.03",
    )
    assert isinstance(got, str)
    assert len(got) == 64


def test_sort_xp_awards_for_payload_uses_canonical_ordering() -> None:
    awards = [
        {
            "xp_reason": "b",
            "distribution_type": "secondary",
            "skill_id": "s2",
            "amount": 10,
        },
        {
            "xp_reason": "a",
            "distribution_type": "theme",
            "theme_id": "t2",
            "source_skill_id": "s2",
            "amount": 5,
        },
        {
            "xp_reason": "a",
            "distribution_type": "primary",
            "skill_id": "s1",
            "amount": 9,
        },
        {
            "xp_reason": "a",
            "distribution_type": "theme",
            "theme_id": "t1",
            "source_skill_id": "s1",
            "amount": 7,
        },
    ]
    sorted_awards = sort_xp_awards_for_payload(awards)
    assert [a["distribution_type"] for a in sorted_awards] == [
        "primary",
        "theme",
        "theme",
        "secondary",
    ]
    assert sorted_awards[1]["theme_id"] == "t1"
    assert sorted_awards[2]["theme_id"] == "t2"


def test_canonical_json_bytes_is_sorted_and_compact() -> None:
    payload = {"b": 2, "a": {"z": 9, "y": 8}}
    out = canonical_json_bytes(payload)
    assert out == b'{"a":{"y":8,"z":9},"b":2}'


def test_canonical_json_bytes_preserves_utf8_non_ascii() -> None:
    payload = {"msg": "cafe cafe\u0301"}
    out = canonical_json_bytes(payload)
    decoded = out.decode("utf-8")
    assert "\\u" not in decoded
    assert decoded.startswith('{"msg":"')


def test_apportion_by_bp_requires_recipients_when_total_positive() -> None:
    with pytest.raises(ValueError, match="sum_bp must be > 0"):
        apportion_by_bp(5, [])


def test_round_half_up_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        round_half_up(-0.1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1])
def test_float_multiplier_to_bp_rejects_invalid_values(bad: float) -> None:
    with pytest.raises(ValueError):
        float_multiplier_to_bp(bad)


def test_float_multiplier_to_bp_clamps_to_max() -> None:
    assert float_multiplier_to_bp(9.99, max_bp=50000) == 50000


def test_finalize_quest_xp_clamps_negative_inputs() -> None:
    result = finalize_quest_xp(
        quest_xp_total=-10,
        troll_bp=-5,
        variety_multiplier_bp=-1,
        arc_reward_multiplier_bp=-2,
        penalty_xp=-100,
    )
    assert result == {
        "quest_xp_total": 0,
        "t1_after_troll": 0,
        "t2_after_variety": 0,
        "t3_after_arc": 0,
        "t4_after_diminishing": 0,
        "penalty_xp": 0,
        "final_xp": 0,
    }


def test_apportion_by_bp_rejects_duplicate_recipient_id() -> None:
    with pytest.raises(ValueError, match="duplicate recipient_id"):
        apportion_by_bp(10, [("a", 5000), ("a", 5000)])


def test_apportion_by_bp_rejects_out_of_range_bp() -> None:
    with pytest.raises(ValueError, match="weight_bp out of bounds"):
        apportion_by_bp(10, [("a", 10001)])


def test_apportion_by_bp_requires_positive_sum_bp_when_total_positive() -> None:
    with pytest.raises(ValueError, match="sum_bp must be > 0"):
        apportion_by_bp(10, [("a", 0), ("b", 0)])


def test_apportion_by_bp_allows_zero_total() -> None:
    assert apportion_by_bp(0, [("a", 10000), ("b", 0)]) == {"a": 0, "b": 0}


def test_apportion_by_bp_zero_total_with_empty_recipients() -> None:
    assert apportion_by_bp(0, []) == {}


def test_choose_primary_recipient_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        choose_primary_recipient_id([])


def test_derive_theme_awards_returns_empty_for_non_positive_skill_xp() -> None:
    assert derive_theme_awards_from_skill_award(0, "s1", [("t1", 10000)]) == []
    assert derive_theme_awards_from_skill_award(-5, "s1", [("t1", 10000)]) == []


def test_derive_theme_awards_drops_zero_amount_rows() -> None:
    rows = derive_theme_awards_from_skill_award(
        source_skill_xp=1,
        source_skill_id="skill_a",
        theme_weights_bp=[("theme_a", 5000), ("theme_b", 5000)],
    )
    assert rows == [
        {
            "distribution_type": "theme",
            "theme_id": "theme_a",
            "source_skill_id": "skill_a",
            "source_skill_xp": 1,
            "amount": 1,
        }
    ]


def test_sort_xp_awards_for_payload_uses_amount_desc_in_tie_group() -> None:
    awards = [
        {
            "xp_reason": "a",
            "distribution_type": "primary",
            "skill_id": "s1",
            "amount": 2,
        },
        {
            "xp_reason": "a",
            "distribution_type": "primary",
            "skill_id": "s1",
            "amount": 10,
        },
    ]
    sorted_awards = sort_xp_awards_for_payload(awards)
    assert [a["amount"] for a in sorted_awards] == [10, 2]


def test_sort_xp_awards_for_payload_handles_missing_keys_defaults() -> None:
    awards = [
        {"amount": 1},
        {"xp_reason": "a", "distribution_type": "primary", "amount": 2},
    ]
    sorted_awards = sort_xp_awards_for_payload(awards)
    assert sorted_awards[0]["amount"] == 1
    assert sorted_awards[1]["amount"] == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "base_xp": -1,
            "minutes": 30,
            "quality_mult": 1.0,
            "variety_bonus": 0.0,
            "troll_multiplier": 1.0,
        },
        {
            "base_xp": 480,
            "minutes": 0,
            "quality_mult": 1.0,
            "variety_bonus": 0.0,
            "troll_multiplier": 1.0,
        },
        {
            "base_xp": 480,
            "minutes": 30,
            "quality_mult": -0.1,
            "variety_bonus": 0.0,
            "troll_multiplier": 1.0,
        },
        {
            "base_xp": 480,
            "minutes": 30,
            "quality_mult": math.nan,
            "variety_bonus": 0.0,
            "troll_multiplier": 1.0,
        },
        {
            "base_xp": 480,
            "minutes": 30,
            "quality_mult": 1.0,
            "variety_bonus": -1.0,
            "troll_multiplier": 1.0,
        },
        {
            "base_xp": 480,
            "minutes": 30,
            "quality_mult": 1.0,
            "variety_bonus": math.inf,
            "troll_multiplier": 1.0,
        },
        {
            "base_xp": 480,
            "minutes": 30,
            "quality_mult": 1.0,
            "variety_bonus": 0.0,
            "troll_multiplier": -0.1,
        },
        {
            "base_xp": 480,
            "minutes": 30,
            "quality_mult": 1.0,
            "variety_bonus": 0.0,
            "troll_multiplier": math.nan,
        },
    ],
)
def test_session_xp_rejects_invalid_inputs(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        calculate_session_xp(**kwargs)


def test_skill_award_identity_key_supports_utf8_inputs() -> None:
    key = build_skill_award_identity_key(
        user_id="u_é",
        entry_id="e_ß",
        quest_id="q_中",
        xp_reason="quest_complete",
        distribution_type="primary",
        skill_id="s_λ",
        ruleset_version="r2026.04",
    )
    assert isinstance(key, str)
    assert len(key) == 64
