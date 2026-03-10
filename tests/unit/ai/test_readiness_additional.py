"""Additional branch coverage for src.ai.readiness."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.ai.readiness as readiness


def test_check_required_imports_reports_missing_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = readiness.importlib.import_module

    def _fake_import(name: str):
        if name == "qdrant_client":
            raise ImportError("missing")
        return real_import(name)

    monkeypatch.setattr(readiness.importlib, "import_module", _fake_import)
    out = readiness.check_required_imports()
    assert out["ok"] is False
    assert "qdrant_client" in out["missing"]


def test_check_required_tools_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness.shutil, "which", lambda _tool: None)
    out = readiness.check_required_tools()
    assert out["ok"] is False
    assert set(out["missing"]) == set(readiness.REQUIRED_TOOLS)


def test_check_seed_contract_detects_missing_seed_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _paths() -> dict[str, Path]:
        return {
            "skills": tmp_path / "missing_skills.jsonl",
            "hierarchy": tmp_path / "missing_hierarchy.jsonl",
            "quests": tmp_path / "missing_quests.jsonl",
            "insights": tmp_path / "missing_insights.jsonl",
            "rag": tmp_path / "missing_rag.jsonl",
            "quest_templates_artifact": tmp_path / "qt.json",
            "theme_mapping_artifact": tmp_path / "tm.json",
        }

    monkeypatch.setattr(readiness, "_seed_paths", _paths)

    out = readiness.check_seed_contract(require_artifacts=False)
    assert out["ok"] is False
    assert len(out["missing_seed_files"]) == 5


def test_check_seed_contract_artifact_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skills = tmp_path / "global_skills_v1.jsonl"
    hierarchy = tmp_path / "global_skill_hierarchy_v1.jsonl"
    quests = tmp_path / "global_quests_v1.jsonl"
    insights = tmp_path / "global_insights_v1.jsonl"
    rag = tmp_path / "rag_documents_v1.jsonl"
    quest_templates = tmp_path / "quest_templates_v1.json"
    theme_mapping = tmp_path / "theme_mapping_v1.json"

    for p in (skills, hierarchy, quests, insights, rag):
        p.write_text("{}\n", encoding="utf-8")
    quest_templates.write_text('{"schema_version": 1}', encoding="utf-8")
    theme_mapping.write_text('{"schema_version": 1}', encoding="utf-8")

    monkeypatch.setattr(
        readiness,
        "_seed_paths",
        lambda: {
            "skills": skills,
            "hierarchy": hierarchy,
            "quests": quests,
            "insights": insights,
            "rag": rag,
            "quest_templates_artifact": quest_templates,
            "theme_mapping_artifact": theme_mapping,
        },
    )

    class _Rows:
        def fetchall(self):
            return []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _stmt):
            return _Rows()

    class _Engine:
        def connect(self):
            return _Conn()

    monkeypatch.setattr(readiness, "engine", _Engine())

    out = readiness.check_seed_contract(require_artifacts=True)
    assert out["ok"] is False
    assert out["missing_artifacts"] == []
    assert len(out["hash_contract_errors"]) == 4


def test_build_readiness_report_v2_flag_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness, "check_python_version", lambda: {"ok": True})
    monkeypatch.setattr(readiness, "check_required_imports", lambda: {"ok": True})
    monkeypatch.setattr(readiness, "check_required_tools", lambda: {"ok": False})
    monkeypatch.setattr(readiness, "check_database_readiness", lambda: {"ok": True})
    monkeypatch.setattr(readiness, "check_ollama_readiness", lambda: {"ok": False})
    monkeypatch.setattr(readiness, "check_qdrant_readiness", lambda: {"ok": True})
    monkeypatch.setattr(
        readiness, "check_seed_contract", lambda require_artifacts: {"ok": False}
    )

    core_mode = readiness.build_readiness_report_v2(require_ai_endpoints=False)
    ai_required = readiness.build_readiness_report_v2(require_ai_endpoints=True)
    runtime_required = readiness.build_readiness_report_v2(require_runtime_deps=True)
    seed_required = readiness.build_readiness_report_v2(require_seed_artifacts=True)

    assert core_mode["ok"] is True
    assert ai_required["ok"] is False
    assert runtime_required["ok"] is False
    assert seed_required["ok"] is False
