"""Import canonical KB master seed files and generate matcher artifacts.

This script is intentionally strict:
- JSONL parsing is line-precise and fails on malformed rows.
- Required fields are validated before any DB writes.
- Cross-file references (hierarchy/quests -> skills) are enforced.
- Upserts are idempotent via source semantic keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.db.models.global_kb import GlobalInsight, GlobalQuest, GlobalSkill
from src.db.models.rag import RagDocument
from src.db.models.server_config import ServerConfig
from src.db.session import db_session, engine


@dataclass(frozen=True)
class SeedPaths:
    skills: Path
    hierarchy: Path
    quests: Path
    insights: Path
    rag: Path
    matcher_dir: Path


def _default_paths(repo_root: Path) -> SeedPaths:
    kb_dir = repo_root / "data" / "seeds" / "kb"
    return SeedPaths(
        skills=kb_dir / "global_skills_v1.jsonl",
        hierarchy=kb_dir / "global_skill_hierarchy_v1.jsonl",
        quests=kb_dir / "global_quests_v1.jsonl",
        insights=kb_dir / "global_insights_v1.jsonl",
        rag=kb_dir / "rag_documents_v1.jsonl",
        matcher_dir=repo_root / "data" / "seeds" / "matcher",
    )


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
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_dt(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        return datetime.now(timezone.utc)
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_flag(value: Any) -> int:
    return 1 if bool(value) else 0


def _load_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing seed file: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number} invalid JSON ({exc.msg})"
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"{path}:{line_number} expected JSON object")
            rows.append(parsed)
    return rows


def _require_fields(rows: list[dict[str, Any]], required: list[str], name: str) -> None:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        for field in required:
            value = row.get(field)
            if value in (None, "") or value == []:
                errors.append(f"{name}[{idx}] missing '{field}'")
                if len(errors) >= 15:
                    break
        if len(errors) >= 15:
            break
    if errors:
        raise ValueError("; ".join(errors))


def _validate_citations(rows: list[dict[str, Any]], key: str, name: str) -> None:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        cites = row.get(key)
        if not isinstance(cites, list) or len(cites) < 2:
            errors.append(f"{name}[{idx}] requires >=2 citations")
            if len(errors) >= 15:
                break
    if errors:
        raise ValueError("; ".join(errors))


def _validate_cross_refs(
    skills: list[dict[str, Any]],
    hierarchy: list[dict[str, Any]],
    quests: list[dict[str, Any]],
) -> None:
    skill_ids = {row["skill_id"] for row in skills}
    errors: list[str] = []

    for idx, row in enumerate(hierarchy, start=1):
        sid = row.get("skill_id")
        if sid not in skill_ids:
            errors.append(f"hierarchy[{idx}] unknown skill_id={sid}")
        parents = row.get("parent_skill_ids", [])
        if parents is None:
            parents = []
        if not isinstance(parents, list):
            errors.append(f"hierarchy[{idx}] parent_skill_ids must be a list")
        else:
            for parent in parents:
                if parent not in skill_ids:
                    errors.append(f"hierarchy[{idx}] unknown parent_skill_id={parent}")
        if len(errors) >= 20:
            break

    for idx, row in enumerate(quests, start=1):
        primary = row.get("primary_skill_id")
        if primary not in skill_ids:
            errors.append(f"quests[{idx}] unknown primary_skill_id={primary}")
        secondary = row.get("secondary_skill_ids")
        if not isinstance(secondary, list):
            errors.append(f"quests[{idx}] secondary_skill_ids must be a list")
        else:
            for sec in secondary:
                if sec not in skill_ids:
                    errors.append(f"quests[{idx}] unknown secondary_skill_id={sec}")
        if len(errors) >= 20:
            break

    if errors:
        raise ValueError("; ".join(errors))


def _short_key(value: str, *, max_len: int = 64) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    if len(key) <= max_len:
        return key
    suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:15]
    return f"{key[:max_len - 16]}_{suffix}"


def _apportion_equal_bp(keys: list[str]) -> dict[str, int]:
    if not keys:
        return {}
    sorted_keys = sorted(keys)
    base = 10000 // len(sorted_keys)
    remainder = 10000 - (base * len(sorted_keys))
    out: dict[str, int] = {k: base for k in sorted_keys}
    for idx in range(remainder):
        out[sorted_keys[idx]] += 1
    return out


def _theme_semantic_key(theme_name: str) -> str:
    return _short_key(f"theme_{theme_name}")


def _extract_first_int(text: str | None, default: int = 1) -> int:
    if not text:
        return default
    match = re.search(r"(\d+)", text)
    if not match:
        return default
    return max(1, int(match.group(1)))


def _build_quest_templates_artifact(quests: list[dict[str, Any]]) -> dict[str, Any]:
    templates: list[dict[str, Any]] = []
    for row in quests:
        kind = row.get("completion_type")
        if kind not in {"cumulative", "recursive"}:
            continue

        template_key = _short_key(str(row["quest_template_id"]))
        skill_key = _short_key(str(row["primary_skill_id"]))
        target_min = _extract_first_int(str(row.get("cadence_or_target") or "1"), 1)
        target_max = max(
            target_min, target_min if kind == "recursive" else target_min * 2
        )

        templates.append(
            {
                "template_key": template_key,
                "skill_semantic_key": skill_key,
                "quest_kind": kind,
                "min_confidence": 65,
                "max_active": 1,
                "cooldown_days": 0,
                "target_range": {"min": target_min, "max": target_max},
                "signals_required": ["has_pattern_hit"],
                "predicate": {"op": "eq", "field": "has_pattern_hit", "value": True},
                "delta_rule": {"type": "fixed", "delta": 1},
                "target_select_rule": "min",
                "score_weights_bp": {
                    "extraction_confidence_score": 6000,
                    "success_quality": 4000,
                },
            }
        )

    templates.sort(key=lambda item: item["template_key"])
    return {"schema_version": 1, "templates": templates}


def _build_theme_mapping_artifact(skills: list[dict[str, Any]]) -> dict[str, Any]:
    mappings: list[dict[str, Any]] = []

    for row in skills:
        skill_key = _short_key(str(row["skill_id"]))
        raw_themes = row.get("related_themes") or []
        if not isinstance(raw_themes, list):
            raw_themes = []
        theme_keys = [
            _theme_semantic_key(str(theme))
            for theme in raw_themes
            if str(theme).strip()
        ]
        theme_weights = _apportion_equal_bp(theme_keys)
        themes = [
            {
                "theme_semantic_key": key,
                "theme_weight_bp": weight,
            }
            for key, weight in sorted(theme_weights.items())
        ]
        mappings.append(
            {
                "skill_semantic_key": skill_key,
                "themes": themes,
            }
        )

    mappings.sort(key=lambda item: item["skill_semantic_key"])
    return {"schema_version": 1, "mappings": mappings}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")


def _ensure_schema_extensions() -> None:
    table_columns = {
        "global_skills": [
            "source_skill_id TEXT",
            "category TEXT",
            "subcategory TEXT",
            "difficulty_baseline TEXT",
            "typical_time_investment_minutes INTEGER",
            "xp_per_session_baseline INTEGER",
            "related_themes_json TEXT",
            "learning_curve_type TEXT",
            "evidence_citations_json TEXT",
            "evidence_grade TEXT",
            "evidence_limitations TEXT",
            "expert_review_priority INTEGER NOT NULL DEFAULT 0",
            "contradiction_flag INTEGER NOT NULL DEFAULT 0",
            "contradiction_type TEXT",
            "contradiction_notes TEXT",
            "hierarchy_level INTEGER",
            "parent_skill_ids_json TEXT",
            "updated_at TIMESTAMP",
        ],
        "global_quests": [
            "source_quest_template_id TEXT",
            "completion_type TEXT",
            "primary_skill_source_id TEXT",
            "secondary_skill_source_ids_json TEXT",
            "difficulty_rating INTEGER",
            "estimated_effort TEXT",
            "xp_reward_min INTEGER",
            "xp_reward_max INTEGER",
            "cadence_or_target TEXT",
            "evidence_citations_json TEXT",
            "evidence_grade TEXT",
            "evidence_limitations TEXT",
            "expert_review_priority INTEGER NOT NULL DEFAULT 0",
            "contradiction_flag INTEGER NOT NULL DEFAULT 0",
            "contradiction_type TEXT",
            "contradiction_notes TEXT",
            "exploit_risk_flag INTEGER NOT NULL DEFAULT 0",
            "notes_for_review TEXT",
            "updated_at TIMESTAMP",
        ],
        "global_insights": [
            "source_insight_id TEXT",
            "category TEXT",
            "strength_initial REAL",
            "trigger_patterns_json TEXT",
            "contraindications_json TEXT",
            "evidence_citations_json TEXT",
            "evidence_grade TEXT",
            "evidence_limitations TEXT",
            "expert_review_priority INTEGER NOT NULL DEFAULT 0",
            "contradiction_flag INTEGER NOT NULL DEFAULT 0",
            "contradiction_type TEXT",
            "contradiction_notes TEXT",
            "updated_at TIMESTAMP",
        ],
        "rag_documents": [
            "source_document_id TEXT",
            "publication_date TEXT",
            "doi_link TEXT",
            "categories_json TEXT",
            "embedding_model TEXT",
            "expert_review_priority INTEGER NOT NULL DEFAULT 0",
            "contradiction_flag INTEGER NOT NULL DEFAULT 0",
            "contradiction_type TEXT",
            "contradiction_notes TEXT",
            "updated_at TIMESTAMP",
        ],
    }

    index_sql = [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_global_skills_source_skill_id ON global_skills(source_skill_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_skills_source_skill_id ON global_skills(source_skill_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_skills_category ON global_skills(category)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_global_quests_source_template_id ON global_quests(source_quest_template_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_quests_source_template_id ON global_quests(source_quest_template_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_quests_completion_type ON global_quests(completion_type)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_global_insights_source_id ON global_insights(source_insight_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_insights_source_id ON global_insights(source_insight_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_insights_category ON global_insights(category)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_documents_source_document_id ON rag_documents(source_document_id)",
        "CREATE INDEX IF NOT EXISTS idx_rag_documents_source_document_id ON rag_documents(source_document_id)",
    ]

    with engine.begin() as conn:
        for table_name, defs in table_columns.items():
            current_cols = {
                row[1]
                for row in conn.execute(
                    text(f"PRAGMA table_info({table_name})")
                ).fetchall()
            }
            for definition in defs:
                column_name = definition.split()[0]
                if column_name in current_cols:
                    continue
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {definition}"))
        for stmt in index_sql:
            conn.execute(text(stmt))


def _upsert_server_config(db, key: str, value: str) -> None:
    row = db.query(ServerConfig).filter(ServerConfig.key == key).one_or_none()
    if row is None:
        db.add(ServerConfig(key=key, value=value))
        return
    row.value = value


def _import_to_db(
    *,
    skills: list[dict[str, Any]],
    hierarchy: list[dict[str, Any]],
    quests: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    rag_docs: list[dict[str, Any]],
    quest_templates_path: Path,
    theme_mapping_path: Path,
    dry_run: bool,
) -> dict[str, int]:
    summary = {
        "skills_inserted": 0,
        "skills_updated": 0,
        "quests_inserted": 0,
        "quests_updated": 0,
        "insights_inserted": 0,
        "insights_updated": 0,
        "rag_inserted": 0,
        "rag_updated": 0,
    }

    if dry_run:
        return summary

    _ensure_schema_extensions()

    hierarchy_by_skill = {row["skill_id"]: row for row in hierarchy}

    with db_session() as db:
        for row in skills:
            source_id = str(row["skill_id"])
            model = (
                db.query(GlobalSkill)
                .filter(GlobalSkill.source_skill_id == source_id)
                .one_or_none()
            )
            if model is None:
                model = GlobalSkill(
                    source_skill_id=source_id,
                    canonical_name=str(row["canonical_name"]),
                )
                db.add(model)
                summary["skills_inserted"] += 1
            else:
                summary["skills_updated"] += 1

            hierarchy_row = hierarchy_by_skill.get(source_id, {})
            model.canonical_name = str(row["canonical_name"])
            model.category = row.get("category")
            model.subcategory = row.get("subcategory")
            model.difficulty_baseline = row.get("difficulty_baseline")
            model.typical_time_investment_minutes = row.get(
                "typical_time_investment_minutes"
            )
            model.xp_per_session_baseline = row.get("xp_per_session_baseline")
            model.related_themes_json = _json_dumps(row.get("related_themes") or [])
            model.learning_curve_type = row.get("learning_curve_type")
            model.description = row.get("description")
            model.evidence_citations_json = _json_dumps(
                row.get("evidence_citations") or []
            )
            model.evidence_grade = row.get("evidence_grade")
            model.evidence_limitations = row.get("evidence_limitations")
            model.expert_review_priority = _as_flag(row.get("expert_review_priority"))
            model.contradiction_flag = _as_flag(row.get("contradiction_flag"))
            model.contradiction_type = row.get("contradiction_type")
            model.contradiction_notes = row.get("contradiction_notes")
            model.hierarchy_level = hierarchy_row.get("hierarchy_level")
            model.parent_skill_ids_json = _json_dumps(
                hierarchy_row.get("parent_skill_ids") or []
            )
            model.created_at = _parse_dt(row.get("created_at"))
            model.updated_at = _parse_dt(row.get("updated_at"))

        for row in quests:
            source_id = str(row["quest_template_id"])
            model = (
                db.query(GlobalQuest)
                .filter(GlobalQuest.quest_key == source_id)
                .one_or_none()
            )
            if model is None:
                model = GlobalQuest(
                    quest_key=source_id, name=str(row["canonical_name"])
                )
                db.add(model)
                summary["quests_inserted"] += 1
            else:
                summary["quests_updated"] += 1

            model.source_quest_template_id = source_id
            model.quest_key = source_id
            model.name = str(row["canonical_name"])
            model.completion_type = row.get("completion_type")
            model.primary_skill_source_id = row.get("primary_skill_id")
            model.secondary_skill_source_ids_json = _json_dumps(
                row.get("secondary_skill_ids") or []
            )
            model.difficulty_rating = row.get("difficulty_rating")
            model.estimated_effort = row.get("estimated_effort")
            model.xp_reward_min = row.get("xp_reward_min")
            model.xp_reward_max = row.get("xp_reward_max")
            model.cadence_or_target = row.get("cadence_or_target")
            model.description = row.get("description")
            model.evidence_citations_json = _json_dumps(
                row.get("evidence_citations") or []
            )
            model.evidence_grade = row.get("evidence_grade")
            model.evidence_limitations = row.get("evidence_limitations")
            model.expert_review_priority = _as_flag(row.get("expert_review_priority"))
            model.contradiction_flag = _as_flag(row.get("contradiction_flag"))
            model.contradiction_type = row.get("contradiction_type")
            model.contradiction_notes = row.get("contradiction_notes")
            model.exploit_risk_flag = _as_flag(row.get("exploit_risk_flag"))
            model.notes_for_review = row.get("notes_for_review")
            model.created_at = _parse_dt(row.get("created_at"))
            model.updated_at = _parse_dt(row.get("updated_at"))

        for row in insights:
            source_id = str(row["insight_id"])
            model = (
                db.query(GlobalInsight)
                .filter(GlobalInsight.insight_key == source_id)
                .one_or_none()
            )
            if model is None:
                model = GlobalInsight(
                    insight_key=source_id,
                    title=source_id.replace("_", " ").title()[:255],
                    description=str(row["insight_text"]),
                )
                db.add(model)
                summary["insights_inserted"] += 1
            else:
                summary["insights_updated"] += 1

            model.source_insight_id = source_id
            model.insight_key = source_id
            model.title = source_id.replace("_", " ").title()[:255]
            model.description = str(row["insight_text"])
            model.category = row.get("category")
            model.strength_initial = row.get("strength_initial")
            model.trigger_patterns_json = _json_dumps(row.get("trigger_patterns") or [])
            model.contraindications_json = _json_dumps(
                row.get("contraindications") or []
            )
            model.evidence_citations_json = _json_dumps(
                row.get("evidence_citations") or []
            )
            model.evidence_grade = row.get("evidence_grade")
            model.evidence_limitations = row.get("evidence_limitations")
            model.expert_review_priority = _as_flag(row.get("expert_review_priority"))
            model.contradiction_flag = _as_flag(row.get("contradiction_flag"))
            model.contradiction_type = row.get("contradiction_type")
            model.contradiction_notes = row.get("contradiction_notes")
            model.created_at = _parse_dt(row.get("created_at"))
            model.updated_at = _parse_dt(row.get("updated_at"))

        for row in rag_docs:
            source_id = str(row["document_id"])
            content = str(row["content_markdown"])
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            model = (
                db.query(RagDocument)
                .filter(RagDocument.source_document_id == source_id)
                .one_or_none()
            )
            if model is None:
                model = RagDocument(
                    source_document_id=source_id,
                    scope="global",
                    owner_user_id=None,
                    title=str(row["title"]),
                    source_citation=str(row.get("source") or ""),
                    content_hash=content_hash,
                    qdrant_collection="rag_documents",
                    qdrant_point_id=source_id,
                    chunk_index=0,
                    body_text=content,
                    verified=1,
                )
                db.add(model)
                summary["rag_inserted"] += 1
            else:
                summary["rag_updated"] += 1

            model.source_document_id = source_id
            model.title = str(row["title"])
            model.source_citation = row.get("source")
            model.publication_date = row.get("publication_date")
            model.doi_link = row.get("doi_link")
            model.categories_json = _json_dumps(row.get("categories") or [])
            model.embedding_model = row.get("embedding_model")
            model.body_text = content
            model.content_hash = content_hash
            model.qdrant_collection = "rag_documents"
            model.qdrant_point_id = source_id
            model.verified = 1
            model.expert_review_priority = _as_flag(row.get("expert_review_priority"))
            model.contradiction_flag = _as_flag(row.get("contradiction_flag"))
            model.contradiction_type = row.get("contradiction_type")
            model.contradiction_notes = row.get("contradiction_notes")
            model.created_at = _parse_dt(row.get("created_at"))
            model.updated_at = _parse_dt(row.get("updated_at"))

        _upsert_server_config(
            db, "quest_matcher.templates_path", str(quest_templates_path.resolve())
        )
        _upsert_server_config(
            db, "quest_matcher.templates_sha256", _sha256(quest_templates_path)
        )
        _upsert_server_config(
            db, "quest_matcher.theme_mapping_path", str(theme_mapping_path.resolve())
        )
        _upsert_server_config(
            db, "quest_matcher.theme_mapping_sha256", _sha256(theme_mapping_path)
        )

    return summary


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

    quest_templates = _build_quest_templates_artifact(quests)
    theme_mapping = _build_theme_mapping_artifact(skills)

    quest_templates_path = paths.matcher_dir / "quest_templates_v1.json"
    theme_mapping_path = paths.matcher_dir / "theme_mapping_v1.json"
    _write_json(quest_templates_path, quest_templates, dry_run=args.dry_run)
    _write_json(theme_mapping_path, theme_mapping, dry_run=args.dry_run)

    db_summary = _import_to_db(
        skills=skills,
        hierarchy=hierarchy,
        quests=quests,
        insights=insights,
        rag_docs=rag_docs,
        quest_templates_path=quest_templates_path,
        theme_mapping_path=theme_mapping_path,
        dry_run=args.dry_run,
    )

    output = {
        "ok": True,
        "dry_run": args.dry_run,
        "files": {
            "skills": str(paths.skills),
            "hierarchy": str(paths.hierarchy),
            "quests": str(paths.quests),
            "insights": str(paths.insights),
            "rag": str(paths.rag),
        },
        "counts": {
            "skills": len(skills),
            "hierarchy": len(hierarchy),
            "quests": len(quests),
            "insights": len(insights),
            "rag": len(rag_docs),
            "quest_templates_artifact": len(quest_templates["templates"]),
            "theme_mapping_artifact": len(theme_mapping["mappings"]),
        },
        "artifacts": {
            "quest_templates_v1": str(quest_templates_path),
            "theme_mapping_v1": str(theme_mapping_path),
            "quest_templates_sha256": (
                _sha256(quest_templates_path) if not args.dry_run else None
            ),
            "theme_mapping_sha256": (
                _sha256(theme_mapping_path) if not args.dry_run else None
            ),
        },
        "db": db_summary,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
