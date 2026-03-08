from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.seeding import import_kb_master as kb_import
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalInsight, GlobalQuest, GlobalSkill
from src.db.models.rag import RagDocument


def _sample_payloads() -> (
    tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]
):
    skills = [
        {
            "skill_id": "skill_python_programming",
            "canonical_name": "Python Programming",
            "category": "Professional",
            "subcategory": "Software Development",
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
            "evidence_limitations": "",
            "expert_review_priority": False,
            "contradiction_flag": False,
            "contradiction_type": "",
            "contradiction_notes": "",
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-02T00:00:00Z",
        },
        {
            "skill_id": "skill_public_speaking",
            "canonical_name": "Public Speaking",
            "category": "Social",
            "subcategory": "Communication",
            "difficulty_baseline": "beginner",
            "typical_time_investment_minutes": 30,
            "xp_per_session_baseline": 480,
            "related_themes": ["Social"],
            "learning_curve_type": "linear",
            "description": "Deliver short structured talks.",
            "evidence_citations": [
                "10.1037/0003-066X.55.1.68",
                "10.1037/0003-066X.57.9.705",
            ],
            "evidence_grade": "A",
            "evidence_limitations": "",
            "expert_review_priority": False,
            "contradiction_flag": False,
            "contradiction_type": "",
            "contradiction_notes": "",
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-02T00:00:00Z",
        },
    ]
    hierarchy = [
        {
            "skill_id": "skill_python_programming",
            "canonical_name": "Python Programming",
            "hierarchy_level": 3,
            "parent_skill_ids": ["skill_public_speaking"],
        },
        {
            "skill_id": "skill_public_speaking",
            "canonical_name": "Public Speaking",
            "hierarchy_level": 2,
            "parent_skill_ids": [],
        },
    ]
    quests = [
        {
            "quest_template_id": "quest_python_streak_7",
            "canonical_name": "7-Day Python Streak",
            "completion_type": "streak",
            "primary_skill_id": "skill_python_programming",
            "secondary_skill_ids": ["skill_public_speaking"],
            "difficulty_rating": 6,
            "estimated_effort": "20 min/day",
            "xp_reward_min": 800,
            "xp_reward_max": 1200,
            "cadence_or_target": "7 consecutive days",
            "description": "Code every day for a week.",
            "evidence_citations": [
                "10.1037/0003-066X.55.1.68",
                "10.1037/0003-066X.57.9.705",
            ],
            "evidence_grade": "A",
            "evidence_limitations": "",
            "expert_review_priority": False,
            "contradiction_flag": False,
            "contradiction_type": "",
            "contradiction_notes": "",
            "exploit_risk_flag": False,
            "notes_for_review": "",
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-02T00:00:00Z",
        },
        {
            "quest_template_id": "quest_python_recursive_3",
            "canonical_name": "Python Recursion Challenge",
            "completion_type": "recursive",
            "primary_skill_id": "skill_python_programming",
            "secondary_skill_ids": [],
            "difficulty_rating": 7,
            "estimated_effort": "45 min",
            "xp_reward_min": 1000,
            "xp_reward_max": 1500,
            "cadence_or_target": "3 reps",
            "description": "Solve recursive tasks repeatedly.",
            "evidence_citations": [
                "10.1037/0003-066X.55.1.68",
                "10.1037/0003-066X.57.9.705",
            ],
            "evidence_grade": "A",
            "evidence_limitations": "",
            "expert_review_priority": False,
            "contradiction_flag": False,
            "contradiction_type": "",
            "contradiction_notes": "",
            "exploit_risk_flag": False,
            "notes_for_review": "",
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-02T00:00:00Z",
        },
    ]
    insights = [
        {
            "insight_id": "insight_focus_plan",
            "insight_text": "Planning concrete next actions improves start rate.",
            "category": "Productivity",
            "strength_initial": 0.8,
            "trigger_patterns": ["overwhelm"],
            "contraindications": [],
            "evidence_citations": [
                "10.1037/0003-066X.57.9.705",
                "10.1037/0003-066X.55.1.68",
            ],
            "evidence_grade": "A",
            "evidence_limitations": "",
            "expert_review_priority": False,
            "contradiction_flag": False,
            "contradiction_type": "",
            "contradiction_notes": "",
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-02T00:00:00Z",
        }
    ]
    rag = [
        {
            "document_id": "rag_doc_focus",
            "title": "Focus Research Brief",
            "source": "Research Journal",
            "publication_date": "2024-01-01",
            "doi_link": "10.1037/0003-066X.57.9.705",
            "content_markdown": "# Focus\n\nA long enough passage for hashing and retrieval context.",
            "categories": ["Productivity"],
            "embedding_model": "all-MiniLM-L6-v2",
            "expert_review_priority": False,
            "contradiction_flag": False,
            "contradiction_type": "",
            "contradiction_notes": "",
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-02T00:00:00Z",
        }
    ]
    return skills, hierarchy, quests, insights, rag


def test_load_jsonl_strict_reports_line_number(tmp_path: Path) -> None:
    file_path = tmp_path / "bad.jsonl"
    file_path.write_text('{"ok":1}\n{"bad":\n', encoding="utf-8")

    with pytest.raises(ValueError, match="bad.jsonl:2"):
        kb_import._load_jsonl_strict(file_path)


def test_import_to_db_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    @contextmanager
    def _db_session():
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr(kb_import, "engine", engine)
    monkeypatch.setattr(kb_import, "db_session", _db_session)

    quest_path = tmp_path / "quest_templates_v1.json"
    theme_path = tmp_path / "theme_mapping_v1.json"
    quest_path.write_text(
        json.dumps({"schema_version": 1, "templates": []}), encoding="utf-8"
    )
    theme_path.write_text(
        json.dumps({"schema_version": 1, "mappings": []}), encoding="utf-8"
    )

    skills, hierarchy, quests, insights, rag = _sample_payloads()

    first = kb_import._import_to_db(
        skills=skills,
        hierarchy=hierarchy,
        quests=quests,
        insights=insights,
        rag_docs=rag,
        quest_templates_path=quest_path,
        theme_mapping_path=theme_path,
        dry_run=False,
    )
    second = kb_import._import_to_db(
        skills=skills,
        hierarchy=hierarchy,
        quests=quests,
        insights=insights,
        rag_docs=rag,
        quest_templates_path=quest_path,
        theme_mapping_path=theme_path,
        dry_run=False,
    )

    assert first["skills_inserted"] == 2
    assert first["quests_inserted"] == 2
    assert first["insights_inserted"] == 1
    assert first["rag_inserted"] == 1

    assert second["skills_updated"] == 2
    assert second["quests_updated"] == 2
    assert second["insights_updated"] == 1
    assert second["rag_updated"] == 1

    with SessionLocal() as db:
        assert db.query(GlobalSkill).count() == 2
        assert db.query(GlobalQuest).count() == 2
        assert db.query(GlobalInsight).count() == 1
        assert db.query(RagDocument).count() == 1


def test_validate_cross_refs_rejects_unknown_skill() -> None:
    skills, hierarchy, quests, _insights, _rag = _sample_payloads()
    quests[0]["primary_skill_id"] = "skill_missing"

    with pytest.raises(ValueError, match="unknown primary_skill_id"):
        kb_import._validate_cross_refs(skills, hierarchy, quests)
