"""Quest API endpoints used by the Week 4 UI/CLI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from src.core.quest_learning import QuestLearningService
from src.db.models.global_kb import GlobalSkill
from src.db.models.quest import Quest
from src.db.models.skill import Skill, SkillThemeMapping
from src.db.models.user import User
from src.db.session import get_db

router = APIRouter(prefix="/quests", tags=["quests"])

_VALID_UI_STATUSES = {"active", "completed", "failed", "abandoned"}


class SkillHierarchyRef(BaseModel):
    source_skill_id: str
    canonical_name: str
    hierarchy_level: Optional[int] = None


class QuestResponse(BaseModel):
    quest_id: str
    user_id: str
    quest_name: str
    description: Optional[str]
    related_skill_name: Optional[str]
    related_skill_source_id: Optional[str]
    related_skill_hierarchy_level: Optional[int]
    related_skill_ancestor_skills: list[SkillHierarchyRef] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    quest_scope: str
    quest_type: str
    status: str
    success_criteria: dict[str, Any]
    current_value: int
    target_value: int
    created_at: datetime
    completed_at: Optional[datetime]


class QuestActionResponse(BaseModel):
    quest_id: str
    status: str
    message: str


def _normalize_status(status: str) -> str:
    # Frontend currently expects only active/completed/failed/abandoned.
    return status if status in _VALID_UI_STATUSES else "failed"


def _parse_string_list(raw_json: Optional[str]) -> list[str]:
    if not raw_json:
        return []
    try:
        parsed = json.loads(raw_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str) and item.strip()]


def _load_global_skill_nodes(
    db: Session,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = (
        db.query(
            GlobalSkill.id,
            GlobalSkill.source_skill_id,
            GlobalSkill.canonical_name,
            GlobalSkill.category,
            GlobalSkill.hierarchy_level,
            GlobalSkill.parent_skill_ids_json,
            GlobalSkill.related_themes_json,
        )
        .all()
    )

    by_id: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_skill_id = str(row.source_skill_id) if row.source_skill_id else None
        related_themes = _parse_string_list(row.related_themes_json)
        if not related_themes and row.category:
            related_themes = [str(row.category)]
        node = {
            "source_skill_id": source_skill_id,
            "canonical_name": row.canonical_name,
            "category": row.category,
            "hierarchy_level": row.hierarchy_level,
            "parent_source_ids": _parse_string_list(row.parent_skill_ids_json),
            "related_themes": related_themes,
        }
        by_id[str(row.id)] = node
        if source_skill_id:
            by_source[source_skill_id] = node

    return by_id, by_source


def _build_ancestor_skill_refs(
    source_skill_id: str,
    global_skills_by_source: dict[str, dict[str, Any]],
) -> list[SkillHierarchyRef]:
    root_node = global_skills_by_source.get(source_skill_id)
    if root_node is None:
        return []

    visited: set[str] = set()
    stack = list(root_node.get("parent_source_ids", []))
    ancestors: list[SkillHierarchyRef] = []

    while stack:
        parent_source_id = stack.pop()
        if parent_source_id in visited:
            continue
        visited.add(parent_source_id)

        parent_node = global_skills_by_source.get(parent_source_id)
        if parent_node is not None:
            ancestors.append(
                SkillHierarchyRef(
                    source_skill_id=parent_source_id,
                    canonical_name=str(parent_node.get("canonical_name") or parent_source_id),
                    hierarchy_level=parent_node.get("hierarchy_level"),
                )
            )
            stack.extend(parent_node.get("parent_source_ids", []))
        else:
            ancestors.append(
                SkillHierarchyRef(
                    source_skill_id=parent_source_id,
                    canonical_name=parent_source_id,
                    hierarchy_level=None,
                )
            )

    return sorted(
        ancestors,
        key=lambda item: (
            item.hierarchy_level if item.hierarchy_level is not None else 10_000,
            item.canonical_name.lower(),
        ),
    )


def _quest_to_response(
    quest: Quest,
    global_skills_by_id: dict[str, dict[str, Any]],
    global_skills_by_source: dict[str, dict[str, Any]],
) -> QuestResponse:
    created_at = quest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    completed_at = quest.completed_at
    if completed_at and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)

    related_skill_name = None
    related_skill_source_id = None
    related_skill_hierarchy_level = None
    related_skill_ancestor_skills: list[SkillHierarchyRef] = []
    related_themes: set[str] = set()
    if quest.skill is not None:
        if quest.skill.name:
            related_skill_name = quest.skill.name

        global_skill_id = quest.skill.global_skill_id
        if global_skill_id:
            global_skill_node = global_skills_by_id.get(global_skill_id)
            if global_skill_node is not None:
                related_skill_source_id = str(global_skill_node["source_skill_id"])
                related_skill_hierarchy_level = global_skill_node["hierarchy_level"]
                for theme_name in global_skill_node.get("related_themes", []):
                    related_themes.add(theme_name)
                if not related_skill_name:
                    related_skill_name = str(
                        global_skill_node.get("canonical_name")
                        or related_skill_source_id
                        or global_skill_id
                    )
                related_skill_ancestor_skills = _build_ancestor_skill_refs(
                    related_skill_source_id, global_skills_by_source
                )
                for ancestor in related_skill_ancestor_skills:
                    ancestor_node = global_skills_by_source.get(ancestor.source_skill_id)
                    if ancestor_node is not None:
                        for theme_name in ancestor_node.get("related_themes", []):
                            related_themes.add(theme_name)

        for mapping in quest.skill.theme_mappings:
            theme = mapping.theme
            if theme is not None and theme.name:
                related_themes.add(theme.name)

    return QuestResponse(
        quest_id=quest.id,
        user_id=quest.user_id,
        quest_name=quest.name,
        description=quest.description,
        related_skill_name=related_skill_name,
        related_skill_source_id=related_skill_source_id,
        related_skill_hierarchy_level=related_skill_hierarchy_level,
        related_skill_ancestor_skills=related_skill_ancestor_skills,
        related_themes=sorted(related_themes),
        # DB quest scope: "instant" | "longterm"
        quest_scope=quest.quest_type,
        # Frontend renders types as one_time/cumulative/recursive/streak.
        quest_type=quest.completion_type,
        status=_normalize_status(quest.status),
        success_criteria={"required_progress": quest.required_progress},
        current_value=quest.current_progress,
        target_value=quest.required_progress,
        created_at=created_at,
        completed_at=completed_at,
    )


@router.get("", response_model=list[QuestResponse], summary="List user quests")
def list_quests(
    user_id: Annotated[str, Query(description="User UUID")],
    status: Annotated[
        Optional[str],
        Query(description="Filter by status: active|completed|failed|abandoned"),
    ] = None,
    db: Session = Depends(get_db),
) -> list[QuestResponse]:
    user_exists = db.query(User.id).filter(User.id == user_id).first()
    if user_exists is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    global_skills_by_id, global_skills_by_source = _load_global_skill_nodes(db)

    query = (
        db.query(Quest)
        .filter(Quest.user_id == user_id)
        .options(
            joinedload(Quest.skill)
            .joinedload(Skill.theme_mappings)
            .joinedload(SkillThemeMapping.theme)
        )
    )
    if status:
        if status not in _VALID_UI_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status {status!r}. Must be one of: {sorted(_VALID_UI_STATUSES)}.",
            )
        query = query.filter(Quest.status == status)

    quests = query.order_by(Quest.created_at.desc()).all()
    return [
        _quest_to_response(q, global_skills_by_id, global_skills_by_source)
        for q in quests
    ]


@router.get("/{quest_id}", response_model=QuestResponse, summary="Get one quest")
def get_quest(
    quest_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> QuestResponse:
    global_skills_by_id, global_skills_by_source = _load_global_skill_nodes(db)

    quest = (
        db.query(Quest)
        .filter(Quest.id == quest_id, Quest.user_id == user_id)
        .options(
            joinedload(Quest.skill)
            .joinedload(Skill.theme_mappings)
            .joinedload(SkillThemeMapping.theme)
        )
        .first()
    )
    if quest is None:
        raise HTTPException(status_code=404, detail=f"Quest {quest_id!r} not found.")
    return _quest_to_response(quest, global_skills_by_id, global_skills_by_source)


@router.post(
    "/{quest_id}/complete",
    response_model=QuestActionResponse,
    summary="Mark a quest as completed",
)
def complete_quest(
    quest_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> QuestActionResponse:
    quest = (
        db.query(Quest).filter(Quest.id == quest_id, Quest.user_id == user_id).first()
    )
    if quest is None:
        raise HTTPException(status_code=404, detail=f"Quest {quest_id!r} not found.")

    if quest.status == "completed":
        return QuestActionResponse(
            quest_id=quest.id,
            status="completed",
            message="Quest already completed.",
        )

    if quest.current_progress < quest.required_progress:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Quest progress incomplete ({quest.current_progress}/{quest.required_progress})."
            ),
        )

    quest.status = "completed"
    completed_at = datetime.now(timezone.utc)
    quest.completed_at = completed_at
    quest.updated_at_utc_ms = int(completed_at.timestamp() * 1000)
    db.add(quest)
    db.commit()

    return QuestActionResponse(
        quest_id=quest.id,
        status="completed",
        message="Quest marked as completed.",
    )


# ---------------------------------------------------------------------------
# Q27: Learning system endpoints (Section 10.3)
# ---------------------------------------------------------------------------


class LearningStatusResponse(BaseModel):
    """Current learning-phase state and per-kind confidence thresholds."""

    learning_complete: bool
    quest_decisions_count: int
    # Thresholds are stored as floats in [0.0, 1.0]
    confidence_threshold_instant: float
    confidence_threshold_streak: float
    confidence_threshold_longterm: float
    can_create_cumulative: bool
    can_create_recursive: bool


@router.get(
    "/learning/status",
    response_model=LearningStatusResponse,
    summary="Get quest learning phase status",
    tags=["quests", "learning"],
)
def get_learning_status(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> LearningStatusResponse:
    """
    Return the current learning-phase state and confidence thresholds.

    Implements Section 10.3 (Q27): new users are in the learning phase until
    they reach the quest-decisions threshold, during which cumulative and
    recursive quests are unavailable.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    status = QuestLearningService(db).get_learning_status(user)
    return LearningStatusResponse(**status)


@router.post(
    "/learning/complete",
    summary="Manually complete the learning phase",
    tags=["quests", "learning"],
)
def complete_learning_phase(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """
    Allow a user to unlock cumulative/recursive quests early by manually
    marking the learning phase complete.

    Idempotent — safe to call if learning is already complete.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    QuestLearningService(db).mark_learning_complete(user)
    return {"learning_complete": True}
