"""Tests for canonical skill rank mapping."""

from src.core.enums import SkillRank, get_rank_from_level


def test_get_rank_from_level_uses_canonical_branch_order() -> None:
    assert get_rank_from_level(1) == SkillRank.F
    assert get_rank_from_level(9) == SkillRank.F
    assert get_rank_from_level(10) == SkillRank.E
    assert get_rank_from_level(11) == SkillRank.E
    assert get_rank_from_level(20) == SkillRank.D
    assert get_rank_from_level(30) == SkillRank.C
    assert get_rank_from_level(40) == SkillRank.B
    assert get_rank_from_level(50) == SkillRank.A
    assert get_rank_from_level(60) == SkillRank.S
    assert get_rank_from_level(75) == SkillRank.SS
    assert get_rank_from_level(100) == SkillRank.SSS
