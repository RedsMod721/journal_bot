"""Validate canonical KB pre-seed files and matcher artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.seeding.import_kb_master import (
    SeedPaths,
    _build_quest_templates_artifact,
    _build_theme_mapping_artifact,
    _default_paths,
    _load_jsonl_strict,
    _require_fields,
    _validate_citations,
    _validate_cross_refs,
)


MIN_COUNTS = {
    "skills": 500,
    "hierarchy": 500,
    "quests": 200,
    "insights": 1000,
    "rag": 1000,
}


def _parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    defaults = _default_paths(repo_root)

    parser = argparse.ArgumentParser()
    parser.add_argument("--skills", default=str(defaults.skills))
    parser.add_argument("--hierarchy", default=str(defaults.hierarchy))
    parser.add_argument("--quests", default=str(defaults.quests))
    parser.add_argument("--insights", default=str(defaults.insights))
    parser.add_argument("--rag", default=str(defaults.rag))
    parser.add_argument("--matcher-dir", default=str(defaults.matcher_dir))
    parser.add_argument("--strict-artifacts", action="store_true")
    return parser.parse_args()


def _load_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} invalid JSON ({exc.msg})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    return payload


def _validate_artifacts(
    *,
    matcher_dir: Path,
    quests: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    strict: bool,
) -> dict[str, Any]:
    quest_templates_path = matcher_dir / "quest_templates_v1.json"
    theme_mapping_path = matcher_dir / "theme_mapping_v1.json"

    generated_quest = _build_quest_templates_artifact(quests)
    generated_theme = _build_theme_mapping_artifact(skills)

    stored_quest = _load_artifact(quest_templates_path)
    stored_theme = _load_artifact(theme_mapping_path)

    if stored_quest.get("schema_version") != 1:
        raise ValueError("quest_templates_v1.json schema_version must be 1")
    if stored_theme.get("schema_version") != 1:
        raise ValueError("theme_mapping_v1.json schema_version must be 1")

    if strict:
        if stored_quest != generated_quest:
            raise ValueError(
                "quest_templates_v1.json is not deterministic against source seeds"
            )
        if stored_theme != generated_theme:
            raise ValueError(
                "theme_mapping_v1.json is not deterministic against source seeds"
            )

    return {
        "quest_templates_path": str(quest_templates_path),
        "theme_mapping_path": str(theme_mapping_path),
        "quest_templates_count": len(stored_quest.get("templates", [])),
        "theme_mappings_count": len(stored_theme.get("mappings", [])),
        "strict_artifacts": strict,
    }


def main() -> int:
    args = _parse_args()
    paths = SeedPaths(
        skills=Path(args.skills),
        hierarchy=Path(args.hierarchy),
        quests=Path(args.quests),
        insights=Path(args.insights),
        rag=Path(args.rag),
        matcher_dir=Path(args.matcher_dir),
    )

    skills = _load_jsonl_strict(paths.skills)
    hierarchy = _load_jsonl_strict(paths.hierarchy)
    quests = _load_jsonl_strict(paths.quests)
    insights = _load_jsonl_strict(paths.insights)
    rag_docs = _load_jsonl_strict(paths.rag)

    _require_fields(
        skills,
        [
            "skill_id",
            "canonical_name",
            "category",
            "difficulty_baseline",
            "typical_time_investment_minutes",
            "xp_per_session_baseline",
            "related_themes",
            "learning_curve_type",
            "description",
            "evidence_citations",
            "evidence_grade",
        ],
        "skills",
    )
    _require_fields(
        hierarchy,
        ["skill_id", "canonical_name", "hierarchy_level"],
        "hierarchy",
    )
    _require_fields(
        quests,
        [
            "quest_template_id",
            "canonical_name",
            "completion_type",
            "primary_skill_id",
            "secondary_skill_ids",
            "difficulty_rating",
            "xp_reward_min",
            "xp_reward_max",
            "cadence_or_target",
            "description",
            "evidence_citations",
            "evidence_grade",
        ],
        "quests",
    )
    _require_fields(
        insights,
        [
            "insight_id",
            "insight_text",
            "category",
            "strength_initial",
            "trigger_patterns",
            "evidence_citations",
            "evidence_grade",
        ],
        "insights",
    )
    _require_fields(
        rag_docs,
        [
            "document_id",
            "title",
            "source",
            "content_markdown",
            "categories",
            "embedding_model",
        ],
        "rag",
    )

    _validate_citations(skills, "evidence_citations", "skills")
    _validate_citations(quests, "evidence_citations", "quests")
    _validate_citations(insights, "evidence_citations", "insights")
    _validate_cross_refs(skills, hierarchy, quests)

    counts = {
        "skills": len(skills),
        "hierarchy": len(hierarchy),
        "quests": len(quests),
        "insights": len(insights),
        "rag": len(rag_docs),
    }

    min_failures = {
        key: {"actual": value, "required_min": MIN_COUNTS[key]}
        for key, value in counts.items()
        if value < MIN_COUNTS[key]
    }
    if min_failures:
        raise ValueError(
            f"seed minimum counts failed: {json.dumps(min_failures, sort_keys=True)}"
        )

    artifacts = _validate_artifacts(
        matcher_dir=paths.matcher_dir,
        quests=quests,
        skills=skills,
        strict=args.strict_artifacts,
    )

    output = {
        "ok": True,
        "counts": counts,
        "minimums": MIN_COUNTS,
        "artifacts": artifacts,
        "paths": {
            "skills": str(paths.skills),
            "hierarchy": str(paths.hierarchy),
            "quests": str(paths.quests),
            "insights": str(paths.insights),
            "rag": str(paths.rag),
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
