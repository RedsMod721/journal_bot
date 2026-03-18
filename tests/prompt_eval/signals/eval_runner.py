"""Eval runner for the signals step (step 07) skill detection.

Runs each EvalEntry from the corpus N times in parallel (threads), calls
signals.run() with a real OllamaClient, and reports precision / recall / F1
and consistency scores.

Usage
-----
# Full eval, default 5 runs per entry (requires Ollama running)
    python -m tests.prompt_eval.signals.eval_runner

# Quick spot-check, 3 runs, specific entries
    python -m tests.prompt_eval.signals.eval_runner --runs 3 --entries phys_neg_01 ment_neg_01

# Save JSON for version comparison
    python -m tests.prompt_eval.signals.eval_runner --runs 5 --output-json eval_v2.json

# Test the v1 (unified) prompt via monkeypatching
    python -m tests.prompt_eval.signals.eval_runner --prompt-version v1 --output-json eval_v1.json

Prompt version switching
------------------------
--prompt-version v1  patches _PROMPT_DETECT_SKILLS in signals.py to the old unified prompt.
                     Uses a single LLM call (v1 architecture) instead of the parallel split.
                     Note: v1 has a {theme_names} placeholder which is already handled by
                     the theme_names="" key in shared_sections.

CI exit codes
-------------
Exit 0  : F1 >= 0.70 threshold
Exit 1  : F1 < 0.70 (prompt regression detected)
Exit 2  : Ollama not reachable
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401 — registers all ORM models
from src.ai.ollama import OllamaClient
from src.ai.steps import signals as signals_module
from src.db.base import Base
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User

from tests.prompt_eval.signals.entries import EVAL_CORPUS, EVAL_ROSTER, EvalEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JSONL_PATH = Path(__file__).parents[3] / "data" / "seeds" / "kb" / "global_skills_v1.jsonl"
_F1_THRESHOLD = 0.70
_EVAL_USER_ID = "00000000-0000-0000-eval-000000000001"

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Raw output of a single signals.run() call."""

    detected_roster_skills: list[str]
    """Skill names matched against the user roster."""

    detected_global_skills: list[str]
    """canonical_names discovered from the KB."""

    raw: dict[str, Any]
    """Full result dict from signals.run()."""

    error: str | None = None
    """Set if the call raised an exception."""


@dataclass
class EntryResult:
    entry: EvalEntry
    runs: list[RunResult]

    # Computed by _score_entry()
    hits: set[str] = field(default_factory=set)
    misses: set[str] = field(default_factory=set)
    fps: set[str] = field(default_factory=set)
    partial_hits: set[str] = field(default_factory=set)
    consistency_score: float = 0.0
    error_count: int = 0


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------


def _build_eval_db() -> tuple[sessionmaker, str]:
    """Create in-memory SQLite DB seeded with GlobalSkills and eval roster.

    Returns (session_factory, user_id). Call factory() in each thread to get
    a fresh Session — never share a Session across threads.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db: Session = factory()

    user = User(
        id=_EVAL_USER_ID,
        email="eval@prompt-eval.internal",
        password_hash="x",
        home_country="US",
    )
    db.add(user)

    # Seed all 12 fixed themes
    _THEME_NAMES = [
        "Physical", "Mental", "Professional", "Social", "Creative",
        "Emotional", "Practical", "Intellectual", "Spiritual",
        "Adventure", "Discipline", "Rest",
    ]
    theme_by_name: dict[str, Theme] = {}
    for name in _THEME_NAMES:
        t = Theme(
            id=str(uuid.uuid4()),
            user_id=_EVAL_USER_ID,
            name=name,
            level=1,
            rank="F",
            xp=0,
        )
        db.add(t)
        theme_by_name[name] = t

    # Seed GlobalSkills from JSONL
    global_by_canonical: dict[str, GlobalSkill] = {}
    if _JSONL_PATH.exists():
        with _JSONL_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                gs = GlobalSkill(
                    id=str(uuid.uuid4()),
                    source_skill_id=row.get("skill_id"),
                    canonical_name=row["canonical_name"],
                    category=row.get("category"),
                    subcategory=row.get("subcategory"),
                    difficulty_baseline=row.get("difficulty_baseline"),
                    typical_time_investment_minutes=row.get("typical_time_investment_minutes"),
                    xp_per_session_baseline=row.get("xp_per_session_baseline"),
                    related_themes_json=json.dumps(row.get("related_themes", [])),
                    learning_curve_type=row.get("learning_curve_type"),
                    description=row.get("description"),
                    evidence_grade=row.get("evidence_grade"),
                    expert_review_priority=bool(row.get("expert_review_priority", False)),
                    contradiction_flag=bool(row.get("contradiction_flag", False)),
                    hierarchy_level=row.get("hierarchy_level"),
                )
                db.add(gs)
                global_by_canonical[gs.canonical_name] = gs
    else:
        print(f"WARNING: GlobalSkill seed file not found at {_JSONL_PATH}", file=sys.stderr)

    db.flush()  # assign PKs before creating FK references

    # Seed eval roster skills (linked to GlobalSkill when available)
    for roster_entry in EVAL_ROSTER:
        name = roster_entry["name"]
        gs = global_by_canonical.get(name)
        skill = Skill(
            id=str(uuid.uuid4()),
            user_id=_EVAL_USER_ID,
            name=name,
            canonical_name=name.lower().replace(" ", "_"),
            level=1,
            rank="F",
            xp=0,
            global_skill_id=gs.id if gs else None,
        )
        db.add(skill)
        db.flush()

        # Link to theme
        theme_name = roster_entry["l1"]
        if theme_name in theme_by_name:
            mapping = SkillThemeMapping(
                id=str(uuid.uuid4()),
                user_id=_EVAL_USER_ID,
                skill_id=skill.id,
                theme_id=theme_by_name[theme_name].id,
            )
            db.add(mapping)

    db.commit()
    db.close()
    return factory, _EVAL_USER_ID


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------


def _run_once(
    entry: EvalEntry,
    session_factory: sessionmaker,
    user_id: str,
    ollama: OllamaClient,
) -> RunResult:
    db: Session = session_factory()
    try:
        result = signals_module.run(
            user_id=user_id,
            canonical_text=entry.content,
            db=db,
            ollama_health={"connected": True, "model_available": True},
            ollama=ollama,
            rag_hits=[],
            qdrant=None,
        )
        # detected_skills and detected_global_skills are lists of strings
        roster_skills = list(result.get("detected_skills", []))
        global_skills = list(result.get("detected_global_skills", []))
        return RunResult(
            detected_roster_skills=roster_skills,
            detected_global_skills=global_skills,
            raw=result,
        )
    except Exception as exc:
        return RunResult(
            detected_roster_skills=[],
            detected_global_skills=[],
            raw={},
            error=str(exc),
        )
    finally:
        db.close()


def _run_entry_n_times(
    entry: EvalEntry,
    session_factory: sessionmaker,
    user_id: str,
    ollama: OllamaClient,
    n: int,
) -> list[RunResult]:
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [
            executor.submit(_run_once, entry, session_factory, user_id, ollama)
            for _ in range(n)
        ]
        return [f.result() for f in as_completed(futures)]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _all_detected_names(run: RunResult) -> set[str]:
    return {s.lower() for s in run.detected_roster_skills + run.detected_global_skills}


def _score_entry(entry: EvalEntry, runs: list[RunResult]) -> EntryResult:
    er = EntryResult(entry=entry, runs=runs)
    er.error_count = sum(1 for r in runs if r.error)

    all_detected: list[set[str]] = [_all_detected_names(r) for r in runs]

    expected_lower = {s.lower() for s in entry.expected_skills}
    excluded_lower = {s.lower() for s in entry.excluded_skills}
    acceptable_lower = {s.lower() for s in entry.acceptable_related}

    # Hit: appears in at least one run
    er.hits = {s for s in expected_lower if any(s in d for d in all_detected)}
    er.misses = expected_lower - er.hits

    # False positive: excluded skill appears in any run
    er.fps = {s for s in excluded_lower if any(s in d for d in all_detected)}

    # Partial credit: acceptable_related detected in any run
    er.partial_hits = {s for s in acceptable_lower if any(s in d for d in all_detected)}

    # Consistency: fraction of runs where ALL expected skills are present
    if expected_lower:
        consistent = sum(1 for d in all_detected if expected_lower.issubset(d))
        er.consistency_score = consistent / len(runs)
    else:
        # For pure negative tests, consistency = fraction of runs with zero FPs
        fp_free = sum(1 for d in all_detected if not excluded_lower.intersection(d))
        er.consistency_score = fp_free / len(runs)

    return er


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _compute_metrics(results: list[EntryResult]) -> dict[str, float | int]:
    positive = [r for r in results if r.entry.expected_skills]

    total_tp = sum(len(r.hits) for r in positive)
    total_fn = sum(len(r.misses) for r in positive)
    total_fp = sum(len(r.fps) for r in results)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    avg_consistency = (
        statistics.mean(r.consistency_score for r in positive)
        if positive else 0.0
    )

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "avg_consistency": round(avg_consistency, 4),
        "total_tp": total_tp,
        "total_fn": total_fn,
        "total_fp": total_fp,
        "n_entries": len(results),
        "n_positive_entries": len(positive),
    }


def _compute_category_breakdown(results: list[EntryResult]) -> dict[str, dict]:
    by_cat: dict[str, list[EntryResult]] = defaultdict(list)
    for r in results:
        by_cat[r.entry.l1_category].append(r)
    return {cat: _compute_metrics(cat_results) for cat, cat_results in sorted(by_cat.items())}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(results: list[EntryResult], metrics: dict, breakdown: dict) -> None:
    W = 72
    print("\n" + "=" * W)
    print("  SIGNALS STEP — PROMPT EVAL REPORT")
    print("=" * W)

    # Per-entry table
    print(f"\n{'ID':<30} {'L1':<14} {'Act':>3} {'Hits':>4} {'Miss':>4} {'FP':>3} {'Cons%':>6}")
    print("-" * W)
    for r in results:
        hit_s = f"{len(r.hits)}/{len(r.entry.expected_skills)}" if r.entry.expected_skills else "n/a"
        miss_s = str(len(r.misses)) if r.entry.expected_skills else "n/a"
        fp_s = str(len(r.fps))
        cons_s = f"{r.consistency_score * 100:.0f}%"
        err_s = f" [ERR:{r.error_count}]" if r.error_count else ""
        print(
            f"{r.entry.id:<30} "
            f"{r.entry.l1_category:<14} "
            f"{r.entry.activity_count:>3} "
            f"{hit_s:>4} "
            f"{miss_s:>4} "
            f"{fp_s:>3} "
            f"{cons_s:>6}"
            f"{err_s}"
        )
        if r.misses:
            print(f"  {'':30} MISSES: {', '.join(sorted(r.misses))}")
        if r.fps:
            print(f"  {'':30} FALSE+: {', '.join(sorted(r.fps))}")
        if r.partial_hits:
            print(f"  {'':30} PARTIAL: {', '.join(sorted(r.partial_hits))}")

    # Aggregate
    print("\n" + "─" * W)
    print(f"  Precision:        {metrics['precision']:.3f}")
    print(f"  Recall:           {metrics['recall']:.3f}")
    print(f"  F1:               {metrics['f1']:.3f}")
    print(f"  Avg Consistency:  {metrics['avg_consistency']:.3f}")
    print(f"  TP={metrics['total_tp']}  FN={metrics['total_fn']}  FP={metrics['total_fp']}")

    # Category breakdown
    print("\n  By L1 Category:")
    for cat, m in breakdown.items():
        print(
            f"    {cat:<14}  P={m['precision']:.2f}  R={m['recall']:.2f}"
            f"  F1={m['f1']:.2f}  cons={m['avg_consistency']:.2f}"
        )
    print("=" * W)


# ---------------------------------------------------------------------------
# Prompt version patching
# ---------------------------------------------------------------------------


def _apply_prompt_version(version: str) -> None:
    """Monkeypatch signals module to use a different prompt version."""
    if version == "v1":
        from src.ai.prompts import SIGNALS_DETECT_SKILLS_V1
        signals_module._PROMPT_DETECT_SKILLS = SIGNALS_DETECT_SKILLS_V1
        # v1 is a unified prompt — patch context prompt to a no-op so the context
        # call returns an empty-ish object without crashing. When running v1,
        # the skills prompt already includes activities/emotions/etc.
        signals_module._PROMPT_DETECT_CONTEXT = (
            "Return a JSON object: "
            '{{"activities":[],"emotions":[],"energy_level":5,"task_type":"analytical","certainty":0.0}}'
        )
        print("INFO: prompt patched to v1 (unified, single LLM call for skills).")
    elif version == "v2":
        from src.ai.prompts import SIGNALS_DETECT_CONTEXT_V2, SIGNALS_DETECT_SKILLS_V2
        signals_module._PROMPT_DETECT_SKILLS = SIGNALS_DETECT_SKILLS_V2
        signals_module._PROMPT_DETECT_CONTEXT = SIGNALS_DETECT_CONTEXT_V2
        print("INFO: prompt set to v2 (default split architecture).")
    else:
        print(f"WARNING: Unknown prompt version '{version}', using current module state.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eval signals step skill detection against a corpus of journal entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--runs", type=int, default=5,
        help="Number of LLM calls per entry for consistency testing (default: 5).",
    )
    parser.add_argument(
        "--entries", nargs="*", metavar="ID",
        help="Run only entries with these IDs. Omit to run all.",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434).",
    )
    parser.add_argument(
        "--model", default=None,
        help="Ollama model name (default: from runtime config).",
    )
    parser.add_argument(
        "--prompt-version", default="v2", choices=["v1", "v2"],
        help="Prompt version to evaluate (default: v2). v1 uses the unified pre-split prompt.",
    )
    parser.add_argument(
        "--output-json", metavar="PATH",
        help="Write aggregate + per-entry results to a JSON file.",
    )
    parser.add_argument(
        "--no-threshold", action="store_true",
        help="Do not exit with code 1 on F1 below threshold.",
    )
    args = parser.parse_args()

    # Apply prompt version before anything else
    _apply_prompt_version(args.prompt_version)

    # Build Ollama client and check health
    ollama_kwargs: dict[str, Any] = {"base_url": args.ollama_url}
    if args.model:
        ollama_kwargs["model"] = args.model
    ollama = OllamaClient(**ollama_kwargs)
    health = ollama.health()
    if not health.get("connected"):
        print(
            f"ERROR: Ollama not reachable at {args.ollama_url}. "
            "Start Ollama before running the eval.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"Ollama connected — model: {ollama.model}")

    # Build in-memory DB
    print("Building eval DB (seeding GlobalSkills + roster)...")
    session_factory, user_id = _build_eval_db()
    print(f"DB ready. Eval user: {user_id}\n")

    # Filter entries
    corpus = EVAL_CORPUS
    if args.entries:
        id_set = set(args.entries)
        corpus = [e for e in corpus if e.id in id_set]
        if not corpus:
            print(f"ERROR: No entries matched IDs: {args.entries}", file=sys.stderr)
            sys.exit(1)

    # Run eval
    all_results: list[EntryResult] = []
    for entry in corpus:
        print(f"  [{entry.id}]  {entry.description} ({args.runs}×)...", flush=True)
        runs = _run_entry_n_times(entry, session_factory, user_id, ollama, n=args.runs)
        result = _score_entry(entry, runs)
        all_results.append(result)
        # Quick inline summary
        hit_str = f"{len(result.hits)}/{len(entry.expected_skills)}" if entry.expected_skills else "n/a"
        fp_str = f"FP={len(result.fps)}"
        cons_str = f"cons={result.consistency_score * 100:.0f}%"
        print(f"    hits={hit_str}  {fp_str}  {cons_str}")

    # Compute and print report
    metrics = _compute_metrics(all_results)
    breakdown = _compute_category_breakdown(all_results)
    _print_report(all_results, metrics, breakdown)

    # Optionally write JSON
    if args.output_json:
        output: dict[str, Any] = {
            "prompt_version": args.prompt_version,
            "runs_per_entry": args.runs,
            "aggregate": metrics,
            "by_category": breakdown,
            "entries": [
                {
                    "id": r.entry.id,
                    "description": r.entry.description,
                    "l1_category": r.entry.l1_category,
                    "activity_count": r.entry.activity_count,
                    "hits": sorted(r.hits),
                    "misses": sorted(r.misses),
                    "false_positives": sorted(r.fps),
                    "partial_hits": sorted(r.partial_hits),
                    "consistency": r.consistency_score,
                    "error_count": r.error_count,
                }
                for r in all_results
            ],
        }
        Path(args.output_json).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"\nResults written to: {args.output_json}")

    # CI threshold gate
    if not args.no_threshold and metrics["f1"] < _F1_THRESHOLD:
        print(
            f"\nFAIL: F1={metrics['f1']:.3f} is below the {_F1_THRESHOLD:.2f} threshold.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
