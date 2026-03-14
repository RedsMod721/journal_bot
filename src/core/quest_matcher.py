"""
Quest matcher core logic.

Implements Section 10.5 (Matching and Creation Algorithm) from architecture.

Global attempt order (Section 10.5.3 — deterministic):
    1. Instant quest completion event creation
    2. Streak contributions + streak quest ensure
    3. Long-term template creations / progression
    4. Recursive successor creations
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

import pytz
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.quest_learning import QuestLearningService
from src.core.quest_template_registry import (
    QuestTemplateDefinition,
    load_quest_template_registry,
)
from src.db.models.global_kb import GlobalSkill
from src.db.models.quest import Quest
from src.db.models.quest_progress import (
    QuestContributionDay,
    QuestContributionEntry,
    QuestProgress,
)
from src.db.models.skill import Skill

if TYPE_CHECKING:
    from src.db.models.journal_entry import JournalEntry
    from src.db.models.user import User

log = logging.getLogger(__name__)

DEFAULT_TEMPLATES_PATH = "data/seeds/matcher/quest_templates_v1.json"
MAX_NEW_QUESTS_PER_ENTRY = 8
MAX_INSTANT_PER_LOCAL_DAY: Optional[int] = None
MAX_PATTERN_HITS_PER_ENTRY = 32
DEFAULT_STREAK_REQUIRED_PROGRESS = 7
DEFAULT_LONGTERM_BASE_XP = 480


@dataclass
class MatchAccumulator:
    created_count: int = 0
    notes: list[str] = field(default_factory=list)
    created_quests: list[Quest] = field(default_factory=list)
    progressed_quests: list[Quest] = field(default_factory=list)
    completed_quests: list[Quest] = field(default_factory=list)
    streak_quests: list[Quest] = field(default_factory=list)

    def add_created(self, quest: Quest | None) -> None:
        if quest is None:
            return
        if all(existing.id != quest.id for existing in self.created_quests):
            self.created_quests.append(quest)
            self.created_count += 1

    def add_progressed(self, quest: Quest | None) -> None:
        if quest is None:
            return
        if all(existing.id != quest.id for existing in self.progressed_quests):
            self.progressed_quests.append(quest)

    def add_completed(self, quest: Quest | None) -> None:
        if quest is None:
            return
        if all(existing.id != quest.id for existing in self.completed_quests):
            self.completed_quests.append(quest)

    def add_streak(self, quest: Quest | None) -> None:
        if quest is None:
            return
        if all(existing.id != quest.id for existing in self.streak_quests):
            self.streak_quests.append(quest)


class QuestMatcherService:
    """Core quest matching and creation logic (Section 10.5)."""

    def __init__(
        self,
        db: Session,
        templates_path: str = DEFAULT_TEMPLATES_PATH,
    ) -> None:
        self.db = db
        self.learning = QuestLearningService(db)
        self.template_registry = load_quest_template_registry(templates_path)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def match_quests_for_entry(
        self,
        user: "User",
        entry: "JournalEntry",
        structured_data: dict,
        requirement_multiplier_bp: int = 10000,
    ) -> dict:
        """
        Match quests for a completed journal entry (Section 10.5).

        Returns a deterministic summary of created, progressed, and completed
        quests. Existing rows are returned when a retry replays the same entry.
        """
        if entry.status != "completed":
            return {"error": "ENTRY_NOT_COMPLETED", "notes": []}

        entry_ts_ms = self._entry_timestamp_ms(entry)
        if entry_ts_ms is None:
            return {"error": "ENTRY_TIME_MISSING", "notes": []}

        local_date = self._get_local_date(entry_ts_ms, user.timezone)
        accumulator = MatchAccumulator()

        accumulator.notes.extend(
            self._expire_stale_longterm_quests(
                user=user,
                local_date=local_date,
                entry_ts_ms=entry_ts_ms,
            )
        )

        instant_quest, instant_note, instant_created = self._attempt_instant_quest(
            user=user,
            entry=entry,
            structured_data=structured_data,
            local_date=local_date,
            created_count=accumulator.created_count,
            entry_ts_ms=entry_ts_ms,
        )
        accumulator.notes.append(instant_note)
        if instant_created:
            accumulator.add_created(instant_quest)
        if instant_quest is not None:
            accumulator.add_completed(instant_quest)

        self._attempt_streak_contributions(
            accumulator=accumulator,
            user=user,
            entry=entry,
            structured_data=structured_data,
            local_date=local_date,
            entry_ts_ms=entry_ts_ms,
            requirement_multiplier_bp=requirement_multiplier_bp,
        )

        self._attempt_longterm_templates(
            accumulator=accumulator,
            user=user,
            entry=entry,
            structured_data=structured_data,
            local_date=local_date,
            entry_ts_ms=entry_ts_ms,
            requirement_multiplier_bp=requirement_multiplier_bp,
        )

        self.db.flush()

        return {
            "instant_quest": instant_quest,
            "streak_quests": accumulator.streak_quests,
            "created_count": accumulator.created_count,
            "notes": accumulator.notes,
            "created_quests": accumulator.created_quests,
            "progressed_quests": accumulator.progressed_quests,
            "completed_quests": accumulator.completed_quests,
        }

    # ------------------------------------------------------------------
    # Step 0 — Expiry / streak break handling
    # ------------------------------------------------------------------

    def _expire_stale_longterm_quests(
        self,
        *,
        user: "User",
        local_date: str,
        entry_ts_ms: int,
    ) -> list[str]:
        notes: list[str] = []
        active_quests: list[Quest] = (
            self.db.query(Quest)
            .filter(
                Quest.user_id == user.id,
                Quest.quest_type == "longterm",
                Quest.status == "active",
            )
            .all()
        )

        current_local_date = date.fromisoformat(local_date)
        for quest in active_quests:
            progress = self._get_or_create_progress(
                user_id=user.id,
                quest=quest,
                required_progress=max(1, int(quest.required_progress or 1)),
                now_ms=entry_ts_ms,
                create_if_missing=False,
            )
            if progress is None:
                continue

            if (
                quest.completion_type == "streak"
                and progress.last_progress_local_date
                and quest.status == "active"
            ):
                previous = date.fromisoformat(progress.last_progress_local_date)
                if (current_local_date - previous).days > 1:
                    self._mark_quest_failed(
                        quest=quest,
                        progress=progress,
                        timestamp_ms=entry_ts_ms,
                    )
                    notes.append(f"STREAK_BROKEN_{quest.id}")
                    continue

            expires_at_utc_ms = getattr(quest, "expires_at_utc_ms", None)
            if (
                quest.status == "active"
                and isinstance(expires_at_utc_ms, int)
                and expires_at_utc_ms > 0
                and entry_ts_ms > expires_at_utc_ms
            ):
                self._mark_quest_expired(
                    quest=quest,
                    progress=progress,
                    timestamp_ms=entry_ts_ms,
                )
                notes.append(f"QUEST_EXPIRED_{quest.id}")

        return notes

    # ------------------------------------------------------------------
    # Step 1 — Instant quest
    # ------------------------------------------------------------------

    def _attempt_instant_quest(
        self,
        *,
        user: "User",
        entry: "JournalEntry",
        structured_data: dict,
        local_date: str,
        created_count: int,
        entry_ts_ms: int,
    ) -> tuple[Optional[Quest], str, bool]:
        allowed, reason = self.learning.check_learning_gate(user, "instant")
        if not allowed:
            return None, f"INSTANT_SKIPPED_{reason}", False

        confidence = self._normalize_confidence_value(
            structured_data.get("extraction_confidence_score", 0.0)
        )
        if confidence is None:
            return None, "INSTANT_SKIPPED_INVALID_CONFIDENCE", False

        ok, reason = self.learning.check_confidence_threshold(user, "instant", confidence)
        if not ok:
            return None, f"INSTANT_SKIPPED_{reason}", False

        if MAX_INSTANT_PER_LOCAL_DAY is not None:
            daily_count = (
                self.db.query(Quest)
                .filter(
                    Quest.user_id == user.id,
                    Quest.quest_type == "instant",
                    Quest.source_local_date == local_date,
                )
                .count()
            )
            if daily_count >= MAX_INSTANT_PER_LOCAL_DAY:
                return None, "INSTANT_SKIPPED_DAILY_CAP", False

        if created_count >= MAX_NEW_QUESTS_PER_ENTRY:
            return None, "INSTANT_SKIPPED_CAP_REACHED", False

        existing = (
            self.db.query(Quest)
            .filter(
                Quest.user_id == user.id,
                Quest.entry_id == entry.id,
                Quest.quest_type == "instant",
            )
            .first()
        )
        if existing:
            return existing, "INSTANT_ENSURED", False

        skill_id = self._get_primary_skill(
            user.id, structured_data.get("skills_weights_bp", {})
        )
        if skill_id is None:
            return None, "INSTANT_SKIPPED_NO_SKILL", False

        now_ms = _now_ms()
        quest = Quest(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_type="instant",
            completion_type="one_time",
            status="completed",
            name=f"Entry {entry.id[:8]} - instant",
            entry_id=entry.id,
            source_local_date=local_date,
            skill_id=skill_id,
            base_xp=480,
            created_from_entry_id=entry.id,
            creation_confidence_bp=min(10000, int(round(confidence * 10000))),
            created_at_utc_ms=now_ms,
            updated_at_utc_ms=now_ms,
            completed_at=datetime.fromtimestamp(entry_ts_ms / 1000, tz=timezone.utc),
            completed_at_utc_ms=entry_ts_ms,
        )

        try:
            with self.db.begin_nested():
                self.db.add(quest)
                self.db.flush()
            return quest, "INSTANT_CREATED", True
        except IntegrityError:
            existing = (
                self.db.query(Quest)
                .filter(
                    Quest.user_id == user.id,
                    Quest.entry_id == entry.id,
                    Quest.quest_type == "instant",
                )
                .first()
            )
            return existing, "INSTANT_ENSURED", False

    # ------------------------------------------------------------------
    # Step 2 — Streak contributions
    # ------------------------------------------------------------------

    def _attempt_streak_contributions(
        self,
        *,
        accumulator: MatchAccumulator,
        user: "User",
        entry: "JournalEntry",
        structured_data: dict,
        local_date: str,
        entry_ts_ms: int,
        requirement_multiplier_bp: int,
    ) -> None:
        raw_hits = structured_data.get("pattern_hits_json", [])
        if isinstance(raw_hits, str):
            try:
                raw_hits = json.loads(raw_hits)
            except (json.JSONDecodeError, TypeError):
                accumulator.notes.append("STREAK_SKIPPED_INVALID_JSON")
                return
        if not isinstance(raw_hits, list):
            accumulator.notes.append("STREAK_SKIPPED_INVALID_FORMAT")
            return

        pattern_hits = self._normalize_pattern_hits(raw_hits)[:MAX_PATTERN_HITS_PER_ENTRY]
        now_ms = _now_ms()

        for hit in pattern_hits:
            semantic_key = self._normalize_semantic_key(hit.get("semantic_key", ""))
            if not semantic_key:
                accumulator.notes.append("STREAK_SKIPPED_EMPTY_SEMANTIC_KEY")
                continue

            confidence = self._normalize_confidence_value(hit.get("confidence_score", 0.0))
            if confidence is None:
                accumulator.notes.append(f"STREAK_SKIPPED_INVALID_CONFIDENCE_{semantic_key}")
                continue

            if not user.learning_phase_complete:
                ok, _ = self.learning.check_confidence_threshold(
                    user, "streak", confidence
                )
                if not ok:
                    accumulator.notes.append(f"STREAK_SKIPPED_CONFIDENCE_{semantic_key}")
                    continue

            existing_quest = (
                self.db.query(Quest)
                .filter(
                    Quest.user_id == user.id,
                    Quest.semantic_key == semantic_key,
                    Quest.quest_type == "longterm",
                    Quest.completion_type == "streak",
                    Quest.status == "active",
                )
                .first()
            )

            if (
                existing_quest is None
                and accumulator.created_count >= MAX_NEW_QUESTS_PER_ENTRY
            ):
                accumulator.notes.append("STREAK_SKIPPED_CAP_REACHED")
                continue

            quest, quest_created = self._ensure_streak_quest(
                user=user,
                semantic_key=semantic_key,
                structured_data=structured_data,
                now_ms=now_ms,
                existing=existing_quest,
                requirement_multiplier_bp=requirement_multiplier_bp,
                created_from_entry_id=entry.id,
            )
            if quest is None:
                accumulator.notes.append(f"STREAK_SKIPPED_ENSURE_FAILED_{semantic_key}")
                continue

            if quest_created:
                accumulator.add_created(quest)
            accumulator.add_streak(quest)

            day_inserted = self._insert_contribution_day(
                user_id=user.id,
                quest_id=quest.id,
                local_date=local_date,
            )
            self._insert_contribution_entry(
                user_id=user.id,
                quest_id=quest.id,
                entry_id=entry.id,
                local_date=local_date,
            )

            if day_inserted:
                completed = self._advance_streak_quest(
                    user=user,
                    quest=quest,
                    local_date=local_date,
                    progress_timestamp_ms=entry_ts_ms,
                )
                accumulator.add_progressed(quest)
                if completed:
                    accumulator.add_completed(quest)

            accumulator.notes.append(f"STREAK_CONTRIBUTED_{semantic_key}")

    def _ensure_streak_quest(
        self,
        *,
        user: "User",
        semantic_key: str,
        structured_data: dict,
        now_ms: int,
        existing: Optional[Quest],
        requirement_multiplier_bp: int,
        created_from_entry_id: str,
    ) -> tuple[Optional[Quest], bool]:
        if existing is not None:
            return existing, False

        skill_id = self._get_primary_skill(
            user.id, structured_data.get("skills_weights_bp", {})
        )
        if skill_id is None:
            return None, False

        required_progress = self._scaled_required_progress(
            DEFAULT_STREAK_REQUIRED_PROGRESS,
            requirement_multiplier_bp,
        )
        quest = Quest(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_type="longterm",
            completion_type="streak",
            status="active",
            name=f"Streak: {semantic_key.replace('_', ' ').title()}",
            semantic_key=semantic_key,
            template_quest_type=f"streak__{semantic_key}",
            instance_key=semantic_key,
            skill_id=skill_id,
            base_xp=DEFAULT_LONGTERM_BASE_XP,
            created_from_entry_id=created_from_entry_id,
            created_at_utc_ms=now_ms,
            updated_at_utc_ms=now_ms,
            current_progress=0,
            required_progress=required_progress,
        )

        progress = QuestProgress(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_id=quest.id,
            progress_value=0,
            required_progress=required_progress,
            streak_current=0,
            streak_best=0,
            updated_at_utc_ms=now_ms,
        )

        try:
            with self.db.begin_nested():
                self.db.add(quest)
                self.db.flush()
                progress.quest_id = quest.id
                self.db.add(progress)
                self.db.flush()
            return quest, True
        except IntegrityError:
            existing = (
                self.db.query(Quest)
                .filter(
                    Quest.user_id == user.id,
                    Quest.semantic_key == semantic_key,
                    Quest.quest_type == "longterm",
                    Quest.completion_type == "streak",
                    Quest.status == "active",
                )
                .first()
            )
            return existing, False

    def _advance_streak_quest(
        self,
        *,
        user: "User",
        quest: Quest,
        local_date: str,
        progress_timestamp_ms: int,
    ) -> bool:
        progress = self._get_or_create_progress(
            user_id=user.id,
            quest=quest,
            required_progress=max(1, int(quest.required_progress or 1)),
            now_ms=progress_timestamp_ms,
        )

        quest.current_progress += 1
        quest.updated_at_utc_ms = progress_timestamp_ms

        progress.progress_value += 1
        progress.streak_current += 1
        progress.streak_best = max(progress.streak_best, progress.streak_current)
        progress.required_progress = max(1, int(quest.required_progress or 1))
        progress.last_progress_local_date = local_date
        progress.last_progress_date = local_date
        progress.updated_at_utc_ms = progress_timestamp_ms

        quest.expires_at_utc_ms = self._end_of_local_day_utc_ms(
            local_date=local_date,
            timezone_str=user.timezone,
            days_ahead=1,
        )

        if quest.current_progress >= quest.required_progress:
            self._mark_quest_completed(
                quest=quest,
                progress=progress,
                timestamp_ms=progress_timestamp_ms,
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Step 3/4 — Long-term templates and recursive successors
    # ------------------------------------------------------------------

    def _attempt_longterm_templates(
        self,
        *,
        accumulator: MatchAccumulator,
        user: "User",
        entry: "JournalEntry",
        structured_data: dict,
        local_date: str,
        entry_ts_ms: int,
        requirement_multiplier_bp: int,
    ) -> None:
        if not user.learning_phase_complete:
            accumulator.notes.append("LONGTERM_SKIPPED_LEARNING_PHASE")
            return

        confidence = self._normalize_confidence_value(
            structured_data.get("extraction_confidence_score", 0.0)
        )
        if confidence is None:
            accumulator.notes.append("LONGTERM_SKIPPED_INVALID_CONFIDENCE")
            return

        ok, reason = self.learning.check_confidence_threshold(
            user, "cumulative", confidence
        )
        if not ok:
            accumulator.notes.append(f"LONGTERM_SKIPPED_{reason}")
            return

        signal_values = self._build_template_signal_values(structured_data)
        matched_skill_keys = self._resolve_skill_semantic_keys(
            user.id, structured_data.get("skills_weights_bp", {})
        )

        candidates: list[tuple[int, QuestTemplateDefinition]] = []
        for template in self.template_registry.templates:
            if confidence < template.min_confidence:
                continue
            if template.skill_semantic_key not in matched_skill_keys:
                continue
            if not self._template_matches(template, signal_values):
                continue
            score = self._calculate_template_score(
                template=template,
                confidence=confidence,
                matched_skill_keys=matched_skill_keys,
            )
            candidates.append((score, template))

        candidates.sort(key=lambda item: (-item[0], item[1].template_key))

        for _score, template in candidates:
            quest = self._find_active_template_quest(user_id=user.id, template=template)
            if quest is None:
                if accumulator.created_count >= MAX_NEW_QUESTS_PER_ENTRY:
                    accumulator.notes.append("LONGTERM_SKIPPED_CAP_REACHED")
                    break
                if self._is_template_on_cooldown(
                    user_id=user.id,
                    template=template,
                    reference_ts_ms=entry_ts_ms,
                ):
                    accumulator.notes.append(
                        f"LONGTERM_SKIPPED_COOLDOWN_{template.template_key}"
                    )
                    continue
                quest = self._create_template_quest(
                    user=user,
                    entry=entry,
                    structured_data=structured_data,
                    template=template,
                    confidence=confidence,
                    requirement_multiplier_bp=requirement_multiplier_bp,
                    created_at_ms=entry_ts_ms,
                )
                if quest is None:
                    accumulator.notes.append(
                        f"LONGTERM_SKIPPED_CREATE_FAILED_{template.template_key}"
                    )
                    continue
                accumulator.add_created(quest)

            entry_inserted = self._insert_contribution_entry(
                user_id=user.id,
                quest_id=quest.id,
                entry_id=entry.id,
                local_date=local_date,
            )
            if not entry_inserted:
                continue

            completed = self._advance_template_quest(
                quest=quest,
                user=user,
                template=template,
                local_date=local_date,
                progress_timestamp_ms=entry_ts_ms,
            )
            accumulator.add_progressed(quest)
            accumulator.notes.append(f"LONGTERM_MATCHED_{template.template_key}")

            if completed:
                accumulator.add_completed(quest)
                if template.quest_kind == "recursive":
                    successor = self._ensure_recursive_successor(
                        user=user,
                        parent_quest=quest,
                        template=template,
                        confidence=confidence,
                        requirement_multiplier_bp=requirement_multiplier_bp,
                        created_at_ms=entry_ts_ms,
                    )
                    if successor is not None:
                        accumulator.add_created(successor)
                        accumulator.notes.append(
                            f"RECURSIVE_SUCCESSOR_CREATED_{template.template_key}"
                        )

    def _create_template_quest(
        self,
        *,
        user: "User",
        entry: "JournalEntry",
        structured_data: dict,
        template: QuestTemplateDefinition,
        confidence: float,
        requirement_multiplier_bp: int,
        created_at_ms: int,
    ) -> Quest | None:
        instance_key = self._find_free_instance_slot(
            user_id=user.id,
            template=template,
        )
        if instance_key is None:
            return None

        skill_id = self._resolve_template_skill_id(
            user_id=user.id,
            template=template,
            skills_weights_bp=structured_data.get("skills_weights_bp", {}),
        )
        if skill_id is None:
            return None

        required_progress = self._scaled_required_progress(
            self._select_target_progress(user.id, template),
            requirement_multiplier_bp,
        )

        quest = Quest(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_type="longterm",
            completion_type=template.quest_kind,
            status="active",
            name=self._template_display_name(template),
            template_quest_type=template.template_key,
            instance_key=instance_key,
            skill_id=skill_id,
            base_xp=DEFAULT_LONGTERM_BASE_XP,
            created_from_entry_id=entry.id,
            creation_confidence_bp=min(10000, int(round(confidence * 10000))),
            created_at_utc_ms=created_at_ms,
            updated_at_utc_ms=created_at_ms,
            current_progress=0,
            required_progress=required_progress,
        )
        progress = QuestProgress(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_id=quest.id,
            progress_value=0,
            required_progress=required_progress,
            updated_at_utc_ms=created_at_ms,
        )

        try:
            with self.db.begin_nested():
                self.db.add(quest)
                self.db.flush()
                progress.quest_id = quest.id
                self.db.add(progress)
                self.db.flush()
            return quest
        except IntegrityError:
            return self._find_active_template_quest(user_id=user.id, template=template)

    def _advance_template_quest(
        self,
        *,
        quest: Quest,
        user: "User",
        template: QuestTemplateDefinition,
        local_date: str,
        progress_timestamp_ms: int,
    ) -> bool:
        progress = self._get_or_create_progress(
            user_id=user.id,
            quest=quest,
            required_progress=max(1, int(quest.required_progress or 1)),
            now_ms=progress_timestamp_ms,
        )
        delta = self._resolve_delta(template)

        quest.current_progress += delta
        quest.updated_at_utc_ms = progress_timestamp_ms

        progress.progress_value += delta
        progress.required_progress = max(1, int(quest.required_progress or 1))
        progress.last_progress_local_date = local_date
        progress.last_progress_date = local_date
        progress.updated_at_utc_ms = progress_timestamp_ms

        if quest.current_progress >= quest.required_progress:
            self._mark_quest_completed(
                quest=quest,
                progress=progress,
                timestamp_ms=progress_timestamp_ms,
            )
            return True

        return False

    def _ensure_recursive_successor(
        self,
        *,
        user: "User",
        parent_quest: Quest,
        template: QuestTemplateDefinition,
        confidence: float,
        requirement_multiplier_bp: int,
        created_at_ms: int,
    ) -> Quest | None:
        successor_key = f"{parent_quest.id}:successor"
        existing = (
            self.db.query(Quest)
            .filter(
                Quest.user_id == user.id,
                Quest.successor_key == successor_key,
            )
            .first()
        )
        if existing is not None:
            return existing

        required_progress = self._scaled_required_progress(
            self._select_target_progress(user.id, template),
            requirement_multiplier_bp,
        )

        quest = Quest(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_type="longterm",
            completion_type="recursive",
            status="active",
            name=self._template_display_name(template),
            template_quest_type=template.template_key,
            instance_key=parent_quest.instance_key,
            successor_key=successor_key,
            skill_id=parent_quest.skill_id,
            base_xp=int(parent_quest.base_xp or DEFAULT_LONGTERM_BASE_XP),
            creation_confidence_bp=min(10000, int(round(confidence * 10000))),
            created_at_utc_ms=created_at_ms,
            updated_at_utc_ms=created_at_ms,
            current_progress=0,
            required_progress=required_progress,
        )
        progress = QuestProgress(
            id=str(uuid.uuid4()),
            user_id=user.id,
            quest_id=quest.id,
            progress_value=0,
            required_progress=required_progress,
            updated_at_utc_ms=created_at_ms,
        )

        try:
            with self.db.begin_nested():
                self.db.add(quest)
                self.db.flush()
                progress.quest_id = quest.id
                self.db.add(progress)
                self.db.flush()
            return quest
        except IntegrityError:
            return (
                self.db.query(Quest)
                .filter(
                    Quest.user_id == user.id,
                    Quest.successor_key == successor_key,
                )
                .first()
            )

    # ------------------------------------------------------------------
    # Day / entry ledger helpers
    # ------------------------------------------------------------------

    def _insert_contribution_day(
        self,
        *,
        user_id: str,
        quest_id: str,
        local_date: str,
    ) -> bool:
        exists = (
            self.db.query(QuestContributionDay)
            .filter(
                QuestContributionDay.user_id == user_id,
                QuestContributionDay.quest_id == quest_id,
                QuestContributionDay.contribution_local_date == local_date,
            )
            .first()
        )
        if exists:
            return False

        row = QuestContributionDay(
            id=str(uuid.uuid4()),
            user_id=user_id,
            quest_id=quest_id,
            contribution_local_date=local_date,
        )
        try:
            with self.db.begin_nested():
                self.db.add(row)
                self.db.flush()
            return True
        except IntegrityError:
            return False

    def _insert_contribution_entry(
        self,
        *,
        user_id: str,
        quest_id: str,
        entry_id: str,
        local_date: str,
    ) -> bool:
        exists = (
            self.db.query(QuestContributionEntry)
            .filter(
                QuestContributionEntry.user_id == user_id,
                QuestContributionEntry.quest_id == quest_id,
                QuestContributionEntry.entry_id == entry_id,
            )
            .first()
        )
        if exists:
            return False

        row = QuestContributionEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            quest_id=quest_id,
            entry_id=entry_id,
            contribution_local_date=local_date,
        )
        try:
            with self.db.begin_nested():
                self.db.add(row)
                self.db.flush()
            return True
        except IntegrityError:
            return False

    # ------------------------------------------------------------------
    # Progress / status helpers
    # ------------------------------------------------------------------

    def _get_or_create_progress(
        self,
        *,
        user_id: str,
        quest: Quest,
        required_progress: int,
        now_ms: int,
        create_if_missing: bool = True,
    ) -> QuestProgress | None:
        progress = (
            self.db.query(QuestProgress)
            .filter(QuestProgress.quest_id == quest.id)
            .first()
        )
        if progress is not None or not create_if_missing:
            return progress

        progress = QuestProgress(
            id=str(uuid.uuid4()),
            user_id=user_id,
            quest_id=quest.id,
            progress_value=int(quest.current_progress or 0),
            required_progress=max(1, required_progress),
            updated_at_utc_ms=now_ms,
        )
        self.db.add(progress)
        self.db.flush()
        return progress

    def _mark_quest_completed(
        self,
        *,
        quest: Quest,
        progress: QuestProgress,
        timestamp_ms: int,
    ) -> None:
        quest.status = "completed"
        quest.completed_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        quest.completed_at_utc_ms = timestamp_ms
        quest.updated_at_utc_ms = timestamp_ms
        progress.updated_at_utc_ms = timestamp_ms
        progress.progress_value = max(progress.progress_value, quest.required_progress)
        progress.required_progress = max(1, int(quest.required_progress or 1))
        if quest.completion_type == "streak":
            progress.streak_current = max(progress.streak_current, quest.required_progress)
            progress.streak_best = max(progress.streak_best, progress.streak_current)
        quest.expires_at_utc_ms = None

    def _mark_quest_expired(
        self,
        *,
        quest: Quest,
        progress: QuestProgress,
        timestamp_ms: int,
    ) -> None:
        quest.status = "expired"
        quest.expired_at_utc_ms = timestamp_ms
        quest.updated_at_utc_ms = timestamp_ms
        progress.updated_at_utc_ms = timestamp_ms

    def _mark_quest_failed(
        self,
        *,
        quest: Quest,
        progress: QuestProgress,
        timestamp_ms: int,
    ) -> None:
        quest.status = "failed"
        quest.updated_at_utc_ms = timestamp_ms
        quest.expires_at_utc_ms = None
        progress.updated_at_utc_ms = timestamp_ms
        progress.streak_current = 0

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    def _build_template_signal_values(self, structured_data: dict) -> dict[str, Any]:
        pattern_hits = structured_data.get("pattern_hits_json", [])
        if isinstance(pattern_hits, str):
            try:
                pattern_hits = json.loads(pattern_hits)
            except (TypeError, ValueError, json.JSONDecodeError):
                pattern_hits = []
        return {
            "has_pattern_hit": bool(pattern_hits),
            "primary_action_type": structured_data.get("primary_action_type"),
            "task_type": structured_data.get("task_type"),
        }

    def _template_matches(
        self,
        template: QuestTemplateDefinition,
        signal_values: dict[str, Any],
    ) -> bool:
        for signal in template.signals_required:
            if signal not in signal_values:
                return False
        return self._predicate_matches(template.predicate, signal_values)

    def _predicate_matches(
        self,
        predicate: dict[str, Any],
        signal_values: dict[str, Any],
    ) -> bool:
        if not predicate:
            return True
        if "all" in predicate:
            items = predicate.get("all") or []
            return all(
                self._predicate_matches(item, signal_values)
                for item in items
                if isinstance(item, dict)
            )
        if "any" in predicate:
            items = predicate.get("any") or []
            return any(
                self._predicate_matches(item, signal_values)
                for item in items
                if isinstance(item, dict)
            )

        field_name = str(predicate.get("field") or "").strip()
        op = str(predicate.get("op") or "eq").strip().lower()
        expected = predicate.get("value")
        actual = signal_values.get(field_name)

        if op == "eq":
            return actual == expected
        if op == "neq":
            return actual != expected
        if op == "truthy":
            return bool(actual)
        if op == "in" and isinstance(expected, list):
            return actual in expected
        return False

    def _calculate_template_score(
        self,
        *,
        template: QuestTemplateDefinition,
        confidence: float,
        matched_skill_keys: set[str],
    ) -> int:
        weights = template.score_weights_bp or {}
        extraction_weight = int(weights.get("extraction_confidence_score", 0))
        skill_weight = int(weights.get("skill_weight_match", 0))
        signal_weight = int(weights.get("confidence_match", 0))

        score = 0
        score += int(round(confidence * extraction_weight))
        if template.skill_semantic_key in matched_skill_keys:
            score += skill_weight
        score += signal_weight
        return score

    def _find_active_template_quest(
        self,
        *,
        user_id: str,
        template: QuestTemplateDefinition,
    ) -> Quest | None:
        return (
            self.db.query(Quest)
            .filter(
                Quest.user_id == user_id,
                Quest.quest_type == "longterm",
                Quest.template_quest_type == template.template_key,
                Quest.completion_type == template.quest_kind,
                Quest.status == "active",
            )
            .order_by(Quest.created_at_utc_ms.asc(), Quest.id.asc())
            .first()
        )

    def _is_template_on_cooldown(
        self,
        *,
        user_id: str,
        template: QuestTemplateDefinition,
        reference_ts_ms: int,
    ) -> bool:
        if template.cooldown_days <= 0:
            return False
        threshold_ms = reference_ts_ms - (template.cooldown_days * 24 * 60 * 60 * 1000)
        recent = (
            self.db.query(Quest.id)
            .filter(
                Quest.user_id == user_id,
                Quest.template_quest_type == template.template_key,
                Quest.quest_type == "longterm",
                Quest.status.in_(("completed", "expired", "failed", "abandoned")),
                Quest.updated_at_utc_ms.isnot(None),
                Quest.updated_at_utc_ms >= threshold_ms,
            )
            .first()
        )
        return recent is not None

    def _find_free_instance_slot(
        self,
        *,
        user_id: str,
        template: QuestTemplateDefinition,
    ) -> str | None:
        active_slots = {
            str(slot)
            for (slot,) in (
                self.db.query(Quest.instance_key)
                .filter(
                    Quest.user_id == user_id,
                    Quest.template_quest_type == template.template_key,
                    Quest.quest_type == "longterm",
                    Quest.status == "active",
                )
                .all()
            )
            if slot
        }
        if template.max_active <= 1:
            instance_key = template.template_key
            return None if instance_key in active_slots else instance_key

        for slot_num in range(1, template.max_active + 1):
            instance_key = f"{template.template_key}#{slot_num}"
            if instance_key not in active_slots:
                return instance_key
        return None

    def _resolve_template_skill_id(
        self,
        *,
        user_id: str,
        template: QuestTemplateDefinition,
        skills_weights_bp: dict,
    ) -> Optional[str]:
        weighted_skill_ids = [
            skill_id for skill_id in skills_weights_bp.keys() if isinstance(skill_id, str)
        ]
        weighted_skills: list[Skill] = []
        if weighted_skill_ids:
            weighted_skills = (
                self.db.query(Skill)
                .filter(Skill.user_id == user_id, Skill.id.in_(weighted_skill_ids))
                .all()
            )

        candidates: list[tuple[int, str]] = []
        for skill in weighted_skills:
            for key in self._skill_candidate_keys(skill):
                if key == template.skill_semantic_key:
                    candidates.append((int(skills_weights_bp.get(skill.id, 0)), skill.id))
                    break

        if candidates:
            max_weight = max(weight for weight, _skill_id in candidates)
            return min(skill_id for weight, skill_id in candidates if weight == max_weight)

        matching_skill = (
            self.db.query(Skill)
            .filter(Skill.user_id == user_id)
            .all()
        )
        for skill in matching_skill:
            if template.skill_semantic_key in self._skill_candidate_keys(skill):
                return skill.id

        return self._get_primary_skill(user_id, skills_weights_bp)

    def _resolve_skill_semantic_keys(
        self,
        user_id: str,
        skills_weights_bp: dict,
    ) -> set[str]:
        skill_ids = [skill_id for skill_id in skills_weights_bp.keys() if isinstance(skill_id, str)]
        if not skill_ids:
            return set()
        skills = (
            self.db.query(Skill)
            .filter(Skill.user_id == user_id, Skill.id.in_(skill_ids))
            .all()
        )
        keys: set[str] = set()
        for skill in skills:
            keys.update(self._skill_candidate_keys(skill))
        return keys

    def _skill_candidate_keys(self, skill: Skill) -> set[str]:
        keys = set()
        canonical = (skill.canonical_name or "").strip().lower().replace(" ", "_")
        if canonical:
            keys.add(canonical)
            keys.add(f"skill_{canonical}")

        source_skill_id: str | None = None
        if skill.global_skill_id:
            source_skill_id = (
                self.db.query(GlobalSkill.source_skill_id)
                .filter(GlobalSkill.id == skill.global_skill_id)
                .scalar()
            )
        if source_skill_id:
            keys.add(str(source_skill_id).strip().lower())
        return keys

    def _select_target_progress(
        self,
        user_id: str,
        template: QuestTemplateDefinition,
    ) -> int:
        if template.target_select_rule == "max":
            return template.target_max
        if template.target_select_rule == "hash_user_template":
            span = template.target_max - template.target_min
            if span <= 0:
                return template.target_min
            digest = hashlib.sha256(f"{user_id}:{template.template_key}".encode()).hexdigest()
            offset = int(digest[:8], 16) % (span + 1)
            return template.target_min + offset
        return template.target_min

    def _resolve_delta(self, template: QuestTemplateDefinition) -> int:
        delta_rule = template.delta_rule or {"type": "fixed", "delta": 1}
        delta_type = str(delta_rule.get("type") or "fixed").lower()
        if delta_type in {"fixed", "increment"}:
            raw = delta_rule.get("delta", delta_rule.get("value", 1))
            try:
                return max(1, int(raw))
            except (TypeError, ValueError):
                return 1
        return 1

    def _template_display_name(self, template: QuestTemplateDefinition) -> str:
        return template.template_key.replace("_", " ").title()

    def _scaled_required_progress(
        self,
        base_required_progress: int,
        requirement_multiplier_bp: int,
    ) -> int:
        scaled = int(round(base_required_progress * max(1, requirement_multiplier_bp) / 10000))
        return max(1, scaled)

    # ------------------------------------------------------------------
    # Skill / confidence / timestamp helpers
    # ------------------------------------------------------------------

    def _get_primary_skill(
        self,
        user_id: str,
        skills_weights_bp: dict,
    ) -> Optional[str]:
        if skills_weights_bp:
            try:
                max_weight = max(int(weight) for weight in skills_weights_bp.values())
                candidates = [
                    str(skill_id)
                    for skill_id, weight in skills_weights_bp.items()
                    if int(weight) == max_weight
                ]
                if candidates:
                    return min(candidates)
            except (ValueError, TypeError):
                pass

        return self._get_fallback_skill(user_id)

    def _get_fallback_skill(self, user_id: str) -> Optional[str]:
        skill = (
            self.db.query(Skill)
            .filter(Skill.user_id == user_id)
            .order_by(Skill.canonical_name.asc(), Skill.id.asc())
            .first()
        )
        if skill is None:
            log.warning("No skills found for user %r - cannot resolve primary skill", user_id)
            return None
        return skill.id

    def _entry_timestamp_ms(self, entry: "JournalEntry") -> Optional[int]:
        ts = entry.processed_at or entry.updated_at or entry.created_at
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int(ts.timestamp() * 1000)

    def _get_local_date(self, timestamp_ms: int, timezone_str: str) -> str:
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            log.warning("Unknown timezone %r; falling back to UTC", timezone_str)
            tz = pytz.UTC

        utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=pytz.UTC)
        return utc_dt.astimezone(tz).strftime("%Y-%m-%d")

    def _end_of_local_day_utc_ms(
        self,
        *,
        local_date: str,
        timezone_str: str,
        days_ahead: int = 0,
    ) -> int:
        local_day = date.fromisoformat(local_date) + timedelta(days=days_ahead)
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.UTC
        local_dt = tz.localize(
            datetime.combine(local_day, time(23, 59, 59, 999000))
        )
        return int(local_dt.astimezone(pytz.UTC).timestamp() * 1000)

    def _normalize_pattern_hits(self, hits: list) -> list[dict[str, Any]]:
        normalized = []
        for idx, hit in enumerate(hits):
            if not isinstance(hit, dict):
                continue
            confidence = self._normalize_confidence_value(hit.get("confidence_score", 0.0))
            if confidence is None:
                continue
            normalized.append(
                {
                    "semantic_key": str(hit.get("semantic_key", "")),
                    "confidence_score": confidence,
                    "_idx": idx,
                }
            )
        normalized.sort(
            key=lambda item: (item["semantic_key"], -item["confidence_score"], item["_idx"])
        )
        return normalized

    def _normalize_semantic_key(self, key: str) -> str:
        if not key:
            return ""
        key = key.lower().replace(" ", "_").replace("-", "_")
        return "".join(char for char in key if char.isalnum() or char == "_")

    def _normalize_confidence_value(self, value: Any) -> Optional[float]:
        try:
            raw = float(value)
        except (TypeError, ValueError):
            return None
        if 0.0 <= raw <= 1.0:
            return raw
        if 1.0 < raw <= 100.0:
            return raw / 100.0
        return None


def _now_ms() -> int:
    """Current UTC time as epoch milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)
