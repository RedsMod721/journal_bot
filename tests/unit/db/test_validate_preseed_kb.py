from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.seeding import import_kb_master as kb_import
from scripts.validation import validate_preseed_kb as kb_validate


def _sample_skills() -> list[dict]:
    return [
        {
            "skill_id": "skill_python_programming",
            "canonical_name": "Python Programming",
            "category": "Professional",
            "difficulty_baseline": "intermediate",
            "typical_time_investment_minutes": 60,
            "xp_per_session_baseline": 1200,
            "related_themes": ["Professional", "Intellectual"],
            "learning_curve_type": "sigmoid",
            "description": "Practice Python fundamentals and applied coding.",
            "evidence_citations": [
                "10.1037/0003-066X.59.1.29",
                "10.1037/0003-066X.55.1.68",
            ],
            "evidence_grade": "A",
        }
    ]


def _sample_quests() -> list[dict]:
    return [
        {
            "quest_template_id": "quest_python_recursive_3",
            "canonical_name": "Python Recursion Challenge",
            "completion_type": "recursive",
            "primary_skill_id": "skill_python_programming",
            "secondary_skill_ids": [],
            "difficulty_rating": 7,
            "xp_reward_min": 1000,
            "xp_reward_max": 1500,
            "cadence_or_target": "3 reps",
            "description": "Solve recursive tasks repeatedly.",
            "evidence_citations": [
                "10.1037/0003-066X.55.1.68",
                "10.1037/0003-066X.57.9.705",
            ],
            "evidence_grade": "A",
        }
    ]


def test_validate_artifacts_strict_passes_for_deterministic_outputs(
    tmp_path: Path,
) -> None:
    matcher_dir = tmp_path / "matcher"
    matcher_dir.mkdir(parents=True, exist_ok=True)

    skills = _sample_skills()
    quests = _sample_quests()

    quest_payload = kb_import._build_quest_templates_artifact(quests)
    theme_payload = kb_import._build_theme_mapping_artifact(skills)

    (matcher_dir / "quest_templates_v1.json").write_text(
        json.dumps(quest_payload, sort_keys=True), encoding="utf-8"
    )
    (matcher_dir / "theme_mapping_v1.json").write_text(
        json.dumps(theme_payload, sort_keys=True), encoding="utf-8"
    )

    result = kb_validate._validate_artifacts(
        matcher_dir=matcher_dir,
        quests=quests,
        skills=skills,
        strict=True,
    )

    assert result["quest_templates_count"] == 1
    assert result["theme_mappings_count"] == 1


def test_validate_artifacts_strict_fails_on_mismatch(tmp_path: Path) -> None:
    matcher_dir = tmp_path / "matcher"
    matcher_dir.mkdir(parents=True, exist_ok=True)

    skills = _sample_skills()
    quests = _sample_quests()

    (matcher_dir / "quest_templates_v1.json").write_text(
        json.dumps({"schema_version": 1, "templates": []}, sort_keys=True),
        encoding="utf-8",
    )
    (matcher_dir / "theme_mapping_v1.json").write_text(
        json.dumps({"schema_version": 1, "mappings": []}, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not deterministic"):
        kb_validate._validate_artifacts(
            matcher_dir=matcher_dir,
            quests=quests,
            skills=skills,
            strict=True,
        )
