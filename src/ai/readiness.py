"""Week 3 readiness probes for DB + AI dependencies."""

from __future__ import annotations

import importlib
import platform
import shutil
import sys
from typing import Any

from sqlalchemy import inspect, text

from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.db.session import engine
from scripts.validation.validate_canonical_schema import (
    CANONICAL_TABLES,
    REQUIRED_COLUMNS,
    REQUIRED_FK_TABLES,
    REQUIRED_INDEX_COLUMNS,
    REQUIRED_SQL_SNIPPETS,
    REQUIRED_TRIGGERS,
    _normalize_sql,
)
from pathlib import Path
import hashlib
import json

REQUIRED_IMPORTS = (
    "httpx",
    "sqlalchemy",
    "yaml",
    "faker",
    "qdrant_client",
    "black",
    "mypy",
    "pytest",
    "ruff",
)

REQUIRED_TOOLS = (
    "black",
    "ruff",
    "mypy",
    "pytest",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _seed_paths() -> dict[str, Path]:
    root = _repo_root()
    return {
        "skills": root / "data" / "seeds" / "kb" / "global_skills_v1.jsonl",
        "hierarchy": root / "data" / "seeds" / "kb" / "global_skill_hierarchy_v1.jsonl",
        "quests": root / "data" / "seeds" / "kb" / "global_quests_v1.jsonl",
        "insights": root / "data" / "seeds" / "kb" / "global_insights_v1.jsonl",
        "rag": root / "data" / "seeds" / "kb" / "rag_documents_v1.jsonl",
        "quest_templates_artifact": root
        / "data"
        / "seeds"
        / "matcher"
        / "quest_templates_v1.json",
        "theme_mapping_artifact": root
        / "data"
        / "seeds"
        / "matcher"
        / "theme_mapping_v1.json",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def check_python_version(min_major: int = 3, min_minor: int = 11) -> dict[str, Any]:
    current = sys.version_info
    ok = (current.major, current.minor) >= (min_major, min_minor)
    return {
        "ok": ok,
        "current": platform.python_version(),
        "required": f">={min_major}.{min_minor}",
    }


def check_required_imports() -> dict[str, Any]:
    missing: list[str] = []
    for module in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(module)
    return {
        "ok": not missing,
        "missing": missing,
        "required": list(REQUIRED_IMPORTS),
    }


def check_required_tools() -> dict[str, Any]:
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    return {
        "ok": not missing,
        "missing": missing,
        "required": list(REQUIRED_TOOLS),
    }


def check_database_readiness() -> dict[str, Any]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_tables = sorted(CANONICAL_TABLES - tables)

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        trigger_rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger'")
        ).fetchall()

    triggers = {row[0] for row in trigger_rows}
    missing_triggers = sorted(REQUIRED_TRIGGERS - triggers)
    missing_columns: list[str] = []
    missing_indexes: list[str] = []
    missing_sql_invariants: list[str] = []
    missing_fks: list[str] = []
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        if table_name not in tables:
            continue
        present_columns = {col["name"] for col in inspector.get_columns(table_name)}
        missing = sorted(required_columns - present_columns)
        if missing:
            missing_columns.append(f"{table_name}: {', '.join(missing)}")

    for table_name, required_indexes in REQUIRED_INDEX_COLUMNS.items():
        if table_name not in tables:
            continue
        indexes = {
            index["name"]: tuple(index.get("column_names") or [])
            for index in inspector.get_indexes(table_name)
        }
        uniques = {
            index["name"]: tuple(index.get("column_names") or [])
            for index in inspector.get_unique_constraints(table_name)
        }
        available = {**indexes, **uniques}
        for index_name, expected_columns in required_indexes.items():
            if available.get(index_name) != expected_columns:
                missing_indexes.append(
                    f"{table_name}.{index_name} -> expected {expected_columns}, found {available.get(index_name)}"
                )

    with engine.connect() as conn:
        sql_rows = conn.execute(
            text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type IN ('table','index') AND sql IS NOT NULL"
            )
        ).fetchall()
    object_sql = {row[0]: _normalize_sql(row[1]) for row in sql_rows}
    for object_name, snippets in REQUIRED_SQL_SNIPPETS.items():
        normalized = object_sql.get(object_name, "")
        for snippet in snippets:
            if _normalize_sql(snippet) not in normalized:
                missing_sql_invariants.append(f"{object_name}: missing `{snippet}`")

    for table_name, required_fks in REQUIRED_FK_TABLES.items():
        if table_name not in tables:
            continue
        fk_rows = inspector.get_foreign_keys(table_name)
        available = {
            tuple(fk.get("constrained_columns") or []): fk.get("referred_table")
            for fk in fk_rows
        }
        for columns, referred_table in required_fks.items():
            if available.get(columns) != referred_table:
                missing_fks.append(
                    f"{table_name}: FK {columns} -> {referred_table} missing (found {available.get(columns)})"
                )

    return {
        "ok": not missing_tables
        and not missing_triggers
        and not missing_columns
        and not missing_indexes
        and not missing_sql_invariants
        and not missing_fks,
        "table_count": len(tables),
        "missing_tables": missing_tables,
        "missing_triggers": missing_triggers,
        "missing_columns": missing_columns,
        "missing_indexes": missing_indexes,
        "missing_sql_invariants": missing_sql_invariants,
        "missing_fks": missing_fks,
    }


def check_ollama_readiness(client: OllamaClient | None = None) -> dict[str, Any]:
    client = client or OllamaClient()
    try:
        health = client.health()
        return {
            "ok": bool(health.get("connected")),
            "connected": bool(health.get("connected")),
            "model_available": bool(health.get("model_available")),
            "models": health.get("models", []),
            "error": health.get("error"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "connected": False,
            "model_available": False,
            "models": [],
            "error": str(exc),
        }


def check_qdrant_readiness(
    adapter: QdrantClientAdapter | None = None,
) -> dict[str, Any]:
    try:
        adapter = adapter or QdrantClientAdapter()
        adapter.ensure_collection()
        # Zero-vector probe for schema/transport sanity; search failures are tolerated.
        probe = adapter.search([0.0] * adapter.vector_size, limit=1)
        return {
            "ok": True,
            "reachable": True,
            "collection": adapter.collection,
            "mode": getattr(adapter, "mode", "remote"),
            "local_path": str(getattr(adapter, "local_path", "")) or None,
            "probe_result_count": len(probe),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "collection": getattr(adapter, "collection", "rag_documents"),
            "mode": getattr(adapter, "mode", "remote"),
            "local_path": str(getattr(adapter, "local_path", "")) or None,
            "probe_result_count": 0,
            "error": str(exc),
        }


def check_seed_contract(require_artifacts: bool = False) -> dict[str, Any]:
    paths = _seed_paths()
    required_seed_keys = ("skills", "hierarchy", "quests", "insights", "rag")
    required_artifact_keys = ("quest_templates_artifact", "theme_mapping_artifact")

    missing_files = [key for key in required_seed_keys if not paths[key].exists()]
    missing_artifacts: list[str] = []
    artifact_schema_errors: list[str] = []
    hash_contract_errors: list[str] = []

    artifacts_found = {}
    if require_artifacts:
        missing_artifacts = [
            key for key in required_artifact_keys if not paths[key].exists()
        ]
        if not missing_artifacts:
            for key in required_artifact_keys:
                path = paths[key]
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if payload.get("schema_version") != 1:
                        artifact_schema_errors.append(f"{key} schema_version must be 1")
                except Exception as exc:
                    artifact_schema_errors.append(f"{key} invalid JSON ({exc})")
            artifacts_found = {
                key: {
                    "path": str(paths[key]),
                    "sha256": _sha256(paths[key]),
                }
                for key in required_artifact_keys
            }
            try:
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT key, value FROM server_config "
                            "WHERE key IN ("
                            "'quest_matcher.templates_path', "
                            "'quest_matcher.templates_sha256', "
                            "'quest_matcher.theme_mapping_path', "
                            "'quest_matcher.theme_mapping_sha256'"
                            ")"
                        )
                    ).fetchall()
                cfg = {row[0]: row[1] for row in rows}
            except Exception as exc:
                cfg = {}
                hash_contract_errors.append(f"server_config lookup failed ({exc})")

            expected = {
                "quest_matcher.templates_path": str(
                    paths["quest_templates_artifact"].resolve()
                ),
                "quest_matcher.templates_sha256": artifacts_found[
                    "quest_templates_artifact"
                ]["sha256"],
                "quest_matcher.theme_mapping_path": str(
                    paths["theme_mapping_artifact"].resolve()
                ),
                "quest_matcher.theme_mapping_sha256": artifacts_found[
                    "theme_mapping_artifact"
                ]["sha256"],
            }
            for cfg_key, expected_value in expected.items():
                current = cfg.get(cfg_key)
                if current != expected_value:
                    hash_contract_errors.append(
                        f"{cfg_key} mismatch (expected={expected_value}, actual={current})"
                    )

    ok = (
        not missing_files
        and not missing_artifacts
        and not artifact_schema_errors
        and not hash_contract_errors
    )

    return {
        "ok": ok,
        "require_artifacts": require_artifacts,
        "seed_files": {
            key: {
                "path": str(paths[key]),
                "exists": paths[key].exists(),
            }
            for key in required_seed_keys
        },
        "artifacts": artifacts_found,
        "missing_seed_files": missing_files,
        "missing_artifacts": missing_artifacts,
        "artifact_schema_errors": artifact_schema_errors,
        "hash_contract_errors": hash_contract_errors,
    }


def build_readiness_report(require_ai_endpoints: bool = False) -> dict[str, Any]:
    return build_readiness_report_v2(
        require_ai_endpoints=require_ai_endpoints,
        require_seed_artifacts=False,
        require_runtime_deps=False,
    )


def build_readiness_report_v2(
    *,
    require_ai_endpoints: bool = False,
    require_seed_artifacts: bool = False,
    require_runtime_deps: bool = False,
) -> dict[str, Any]:
    python_check = check_python_version()
    imports_check = check_required_imports()
    tools_check = check_required_tools()
    db_check = check_database_readiness()
    ollama_check = check_ollama_readiness()
    qdrant_check = check_qdrant_readiness()
    seed_check = check_seed_contract(require_artifacts=require_seed_artifacts)

    core_ok = python_check["ok"] and imports_check["ok"] and db_check["ok"]
    if require_runtime_deps:
        core_ok = core_ok and tools_check["ok"]
    if require_seed_artifacts:
        core_ok = core_ok and seed_check["ok"]
    ai_ok = ollama_check["ok"] and qdrant_check["ok"]

    if require_ai_endpoints:
        overall_ok = core_ok and ai_ok
    else:
        overall_ok = core_ok

    return {
        "ok": overall_ok,
        "require_ai_endpoints": require_ai_endpoints,
        "require_seed_artifacts": require_seed_artifacts,
        "require_runtime_deps": require_runtime_deps,
        "checks": {
            "python": python_check,
            "imports": imports_check,
            "tools": tools_check,
            "database": db_check,
            "seed_contract": seed_check,
            "ollama": ollama_check,
            "qdrant": qdrant_check,
        },
    }
