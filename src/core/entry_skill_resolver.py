"""Resolve journal-entry signals into source skill weights.

This module bridges lightweight activity detection and the canonical global
skill graph so pipeline runtimes can produce stable, replayable skill-routing
payloads even when the user does not already have matching Skill rows.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from sqlalchemy.orm import Session

from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill


@dataclass(frozen=True)
class EntrySkillResolution:
    """Structured skill-routing result for one journal entry."""

    source_skills_weights_bp: dict[str, int]
    skills_weights_bp: dict[str, int]
    resolved_skill_names: list[str]
    pattern_hits_json: list[dict[str, str | float]]
    extraction_confidence_score: float


def resolve_entry_skill_signals(
    *,
    user_id: str,
    canonical_text: str,
    detected_skills: Iterable[str],
    detected_activities: Iterable[str],
    detected_global_skill_ids: Iterable[str] = (),
    detected_skill_weights: dict[str, float] | None = None,
    detected_global_skill_weights: dict[str, float] | None = None,
    db: Session,
) -> EntrySkillResolution:
    """Resolve entry signals into source-skill and user-skill weights.

    Resolution order:
        1+2. LLM-detected user skills (linked to GlobalSkill) and LLM-discovered
             new GlobalSkill IDs are merged so discovery is never blocked by
             existing roster matches. Weights are proportional to LLM confidence.
        3. Existing detected legacy user skills with no GlobalSkill link.
        4. Explicit activity routing from journal text and detected activities.
    """
    _skill_w: dict[str, float] = detected_skill_weights or {}
    _global_w: dict[str, float] = detected_global_skill_weights or {}

    pattern_hits = _build_pattern_hits(detected_activities)
    skills = db.query(Skill).filter(Skill.user_id == user_id).all()
    globals_by_id = _load_global_rows_by_id(skills=skills, db=db)

    detected_skill_names = {
        _normalize_label(name)
        for name in detected_skills
        if _normalize_label(name)
    }

    matched_skills = [
        skill
        for skill in skills
        if detected_skill_names.intersection(_skill_candidate_labels(skill))
    ]
    detected_sources = sorted(
        {
            str(globals_by_id[skill.global_skill_id].source_skill_id)
            for skill in matched_skills
            if skill.global_skill_id
            and skill.global_skill_id in globals_by_id
            and globals_by_id[skill.global_skill_id].source_skill_id
        }
    )
    legacy_skill_ids = sorted(
        {
            str(skill.id)
            for skill in matched_skills
            if not skill.global_skill_id or skill.global_skill_id not in globals_by_id
        }
    )

    # Priority 1 + 2: LLM-detected user skills (linked to GlobalSkill) and
    # LLM-discovered new GlobalSkill IDs are merged so that skill discovery is
    # never blocked by existing roster matches.
    direct_global_ids = [
        str(sid).strip()
        for sid in detected_global_skill_ids
        if str(sid).strip()
    ]
    if direct_global_ids:
        available = _load_global_rows_by_source(
            source_skill_ids=direct_global_ids, db=db
        )
        valid_discovery_ids = sorted({sid for sid in direct_global_ids if sid in available})
    else:
        valid_discovery_ids = []

    # Combine: existing-user-skill sources + newly discovered global sources
    combined_sources = sorted(set(detected_sources) | set(valid_discovery_ids))
    if combined_sources:
        # Build source_skill_id → int score from LLM float weights.
        # Scale by 1000 — _allocate_weighted_basis_points only needs relative
        # proportions and rescales to 10000 internally.
        combined_weight_scores: dict[str, int] = {}
        for skill in matched_skills:
            if not skill.global_skill_id or skill.global_skill_id not in globals_by_id:
                continue
            gs = globals_by_id[str(skill.global_skill_id)]
            if gs.source_skill_id:
                sid = str(gs.source_skill_id)
                raw_w = _skill_w.get(skill.name, 0.0) or _skill_w.get(
                    _normalize_label(skill.name), 0.0
                )
                combined_weight_scores[sid] = max(1, round(raw_w * 1000))
        for sid in valid_discovery_ids:
            if sid not in combined_weight_scores:  # don't overwrite P1 weight
                raw_w = _global_w.get(sid, 0.0)
                combined_weight_scores[sid] = max(1, round(raw_w * 1000))

        source_weights = (
            _allocate_weighted_basis_points(combined_weight_scores)
            if combined_weight_scores
            else _allocate_equal_basis_points(combined_sources)
        )
        user_skill_weights = _map_source_weights_to_user_skills(
            user_id=user_id,
            source_weights_bp=source_weights,
            db=db,
        )
        confidence = 0.85 if valid_discovery_ids else 0.80
        return EntrySkillResolution(
            source_skills_weights_bp=source_weights,
            skills_weights_bp=user_skill_weights,
            resolved_skill_names=_ordered_skill_names(source_weights, db=db),
            pattern_hits_json=pattern_hits,
            extraction_confidence_score=confidence,
        )

    # Priority 3: legacy user skills (no global link)
    if legacy_skill_ids:
        return EntrySkillResolution(
            source_skills_weights_bp={},
            skills_weights_bp=_allocate_equal_basis_points(legacy_skill_ids),
            resolved_skill_names=sorted({str(skill.name) for skill in matched_skills}),
            pattern_hits_json=pattern_hits,
            extraction_confidence_score=0.80,
        )

    # Priority 4: hardcoded activity routing
    activity_source_scores = _activity_source_scores(
        canonical_text=canonical_text,
        detected_activities=detected_activities,
        db=db,
    )
    activity_source_weights = _allocate_weighted_basis_points(activity_source_scores)
    return EntrySkillResolution(
        source_skills_weights_bp=activity_source_weights,
        skills_weights_bp=_map_source_weights_to_user_skills(
            user_id=user_id,
            source_weights_bp=activity_source_weights,
            db=db,
        ),
        resolved_skill_names=_ordered_skill_names(activity_source_weights, db=db),
        pattern_hits_json=pattern_hits,
        extraction_confidence_score=(
            0.80 if activity_source_weights else (0.65 if pattern_hits else 0.0)
        ),
    )


def _normalize_label(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_pattern_key(raw: str) -> str:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(ch for ch in key if ch.isalnum() or ch == "_")


def _build_pattern_hits(detected_activities: Iterable[str]) -> list[dict[str, str | float]]:
    pattern_hits: list[dict[str, str | float]] = []
    seen: set[str] = set()
    for activity in sorted(
        {
            _normalize_label(activity)
            for activity in detected_activities
            if _normalize_label(activity)
        }
    ):
        semantic_key = _normalize_pattern_key(activity)
        if semantic_key and semantic_key not in seen:
            pattern_hits.append({"semantic_key": semantic_key, "confidence_score": 0.70})
            seen.add(semantic_key)
    return pattern_hits


def _skill_candidate_labels(skill: Skill) -> set[str]:
    labels = {
        _normalize_label(skill.name),
        _normalize_label(skill.canonical_name),
        _normalize_label(str(skill.canonical_name or "").replace("_", " ")),
    }
    return {label for label in labels if label}


def _load_global_rows_by_id(*, skills: list[Skill], db: Session) -> dict[str, GlobalSkill]:
    global_ids = sorted({str(skill.global_skill_id) for skill in skills if skill.global_skill_id})
    if not global_ids:
        return {}
    rows = db.query(GlobalSkill).filter(GlobalSkill.id.in_(global_ids)).all()
    return {str(row.id): row for row in rows}


def _load_global_rows_by_source(
    *, source_skill_ids: Iterable[str], db: Session
) -> dict[str, GlobalSkill]:
    ordered_ids = sorted({str(skill_id) for skill_id in source_skill_ids if str(skill_id).strip()})
    if not ordered_ids:
        return {}
    rows = (
        db.query(GlobalSkill)
        .filter(GlobalSkill.source_skill_id.in_(ordered_ids))
        .all()
    )
    return {
        str(row.source_skill_id): row
        for row in rows
        if row.source_skill_id
    }


def _activity_source_scores(
    *,
    canonical_text: str,
    detected_activities: Iterable[str],
    db: Session,
) -> dict[str, int]:
    lowered = canonical_text.lower()
    activities = {
        _normalize_label(activity)
        for activity in detected_activities
        if _normalize_label(activity)
    }
    candidate_scores: dict[str, int] = {}

    def add_weight(source_skill_id: str, amount: int) -> None:
        if amount <= 0:
            return
        candidate_scores[source_skill_id] = candidate_scores.get(source_skill_id, 0) + amount

    cardio_context = any(
        marker in lowered for marker in ("cardio", "endurance", "aerobic")
    )
    strength_context = bool(
        activities.intersection(
            {"pushup", "strength_training", "workout", "exercise"}
        )
        or any(
            marker in lowered
            for marker in (
                "pushup",
                "push-up",
                "strength training",
                "resistance training",
                "weights",
                "lifting",
            )
        )
    )
    if "run" in activities:
        add_weight("skill_physical_running", 7000 if cardio_context else 10000)
        if cardio_context:
            add_weight("skill_physical_cardio_endurance", 1500)
            add_weight("skill_physical_cardiorespiratory_fitness", 1500)
    elif cardio_context:
        add_weight("skill_physical_cardio_endurance", 7000)
        add_weight("skill_physical_cardiorespiratory_fitness", 3000)

    if strength_context:
        add_weight("skill_physical_strength_training", 7000 if cardio_context else 10000)
        if cardio_context:
            add_weight("skill_physical_cardio_endurance", 1500)
            add_weight("skill_physical_cardiorespiratory_fitness", 1500)

    if "code" in activities:
        add_weight("skill_professional_programming", 10000)
    if "write" in activities:
        add_weight("skill_creative_writing", 10000)
    if "meditate" in activities:
        add_weight("skill_mental_meditation", 10000)

    available_globals = _load_global_rows_by_source(
        source_skill_ids=candidate_scores.keys(),
        db=db,
    )
    return {
        source_skill_id: score
        for source_skill_id, score in candidate_scores.items()
        if source_skill_id in available_globals
    }


def _allocate_equal_basis_points(recipient_ids: list[str]) -> dict[str, int]:
    if not recipient_ids:
        return {}
    ordered = sorted(recipient_ids)
    base = 10000 // len(ordered)
    remainder = 10000 - (base * len(ordered))
    return {
        recipient_id: base + (1 if index < remainder else 0)
        for index, recipient_id in enumerate(ordered)
    }


def _allocate_weighted_basis_points(weight_scores: dict[str, int]) -> dict[str, int]:
    if not weight_scores:
        return {}

    positive = {sid: int(score) for sid, score in weight_scores.items() if int(score) > 0}
    if not positive:
        return {}

    total = sum(positive.values())
    allocations: dict[str, int] = {}
    remainders: list[tuple[int, str]] = []
    assigned = 0
    for skill_id in sorted(positive):
        scaled = positive[skill_id] * 10000
        basis_points = scaled // total
        allocations[skill_id] = basis_points
        assigned += basis_points
        remainders.append((scaled % total, skill_id))

    remainders.sort(key=lambda item: (-item[0], item[1]))
    remaining = 10000 - assigned
    idx = 0
    while remaining > 0:
        _, skill_id = remainders[idx % len(remainders)]
        allocations[skill_id] += 1
        remaining -= 1
        idx += 1
    return allocations


def _map_source_weights_to_user_skills(
    *,
    user_id: str,
    source_weights_bp: dict[str, int],
    db: Session,
) -> dict[str, int]:
    if not source_weights_bp:
        return {}

    globals_by_source = _load_global_rows_by_source(
        source_skill_ids=source_weights_bp.keys(),
        db=db,
    )
    if not globals_by_source:
        return {}

    global_to_user_skill: dict[str, Skill] = {}
    global_ids = sorted({str(row.id) for row in globals_by_source.values()})
    if global_ids:
        rows = (
            db.query(Skill)
            .filter(Skill.user_id == user_id, Skill.global_skill_id.in_(global_ids))
            .order_by(Skill.id.asc())
            .all()
        )
        for skill in rows:
            global_id = str(skill.global_skill_id)
            global_to_user_skill.setdefault(global_id, skill)

    mapped: dict[str, int] = {}
    for source_skill_id, weight in source_weights_bp.items():
        global_row = globals_by_source.get(source_skill_id)
        if global_row is None:
            continue
        user_skill = global_to_user_skill.get(str(global_row.id))
        if user_skill is None:
            continue
        mapped[str(user_skill.id)] = mapped.get(str(user_skill.id), 0) + int(weight)
    return mapped


def _ordered_skill_names(source_weights_bp: dict[str, int], *, db: Session) -> list[str]:
    if not source_weights_bp:
        return []
    globals_by_source = _load_global_rows_by_source(
        source_skill_ids=source_weights_bp.keys(),
        db=db,
    )
    def _sort_key(source_skill_id: str) -> tuple[int, str]:
        global_row = globals_by_source.get(source_skill_id)
        fallback_name = source_skill_id
        canonical_name = (
            str(global_row.canonical_name)
            if global_row is not None and global_row.canonical_name
            else fallback_name
        )
        return (-int(source_weights_bp[source_skill_id]), canonical_name)

    ordered = sorted(source_weights_bp, key=_sort_key)
    names: list[str] = []
    for source_skill_id in ordered:
        global_row = globals_by_source.get(source_skill_id)
        if global_row is None:
            continue
        name = str(global_row.canonical_name)
        if name not in names:
            names.append(name)
    return names
