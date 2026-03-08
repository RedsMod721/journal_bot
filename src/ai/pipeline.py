"""Week 3 17-step AI pipeline with persistence contracts."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from src.ai.cache import StepCache
from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.core.quests import match_quests
from src.core.xp import (
    build_skill_award_identity_key,
    build_theme_award_identity_key,
    derive_theme_awards_from_skill_award,
    finalize_quest_xp,
)
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.processing import (
    EntryIdempotencyClaim,
    OutboxEvent,
    ProcessingJob,
    ProcessingJobAttempt,
)
from src.db.models.quest import Quest
from src.db.models.quest_progress import QuestProgress
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.xp import XpAward

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "week3-v1"
RULESET_VERSION = "s10-v8"


class PipelineStepError(RuntimeError):
    """Raised when a mandatory pipeline step fails."""

    def __init__(self, step_name: str, error_code: str, message: str) -> None:
        super().__init__(message)
        self.step_name = step_name
        self.error_code = error_code


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso8601z(ts: datetime) -> str:
    return (
        ts.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class PipelineProcessor:
    """Canonical processing wrapper with idempotency + outbox + job attempts."""

    def __init__(
        self,
        db: Session,
        ollama: OllamaClient | None = None,
        qdrant: QdrantClientAdapter | None = None,
        cache: StepCache | None = None,
    ) -> None:
        self.db = db
        self.ollama = ollama or OllamaClient()
        self.qdrant = qdrant or self._build_default_qdrant()
        self.cache = cache or StepCache(ttl_hours=24)

    @staticmethod
    def _build_default_qdrant() -> Any:
        try:
            return QdrantClientAdapter()
        except Exception:

            class _NoQdrant:
                def ensure_collection(self) -> None:
                    return None

                def search(
                    self, _vector: list[float], limit: int = 5
                ) -> list[dict[str, Any]]:
                    return []

            return _NoQdrant()

    def process_entry(
        self, entry_id: str, user_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        replay = self._get_idempotent_replay(user_id, idempotency_key)
        if replay is not None:
            return replay

        processing_run_id = str(uuid.uuid4())

        entry = self._get_entry(user_id=user_id, entry_id=entry_id)
        if entry is None:
            raise PipelineStepError(
                "validate_input",
                "ENTRY_NOT_FOUND",
                f"journal entry {entry_id} for user {user_id} not found",
            )

        self._claim_idempotency(user_id, entry_id, idempotency_key, processing_run_id)
        job = self._upsert_job(user_id, entry_id, processing_run_id)
        self._create_attempt(job.id, 1, status="started")

        entry.status = "processing"
        entry.error_message = None
        self.db.commit()

        try:
            result = self._run_steps(
                entry_id=entry_id, user_id=user_id, processing_run_id=processing_run_id
            )
            job.status = "completed"
            job.result_json = json.dumps(result, sort_keys=True)
            self._create_attempt(job.id, 2, status="completed")
            self._mark_claim_completed(user_id, idempotency_key)
            self._emit_outbox_event(
                user_id=user_id, event_type="entry.processed", payload=result
            )
            self.db.commit()
            logger.info(
                "pipeline completed run=%s user=%s entry=%s idempotency=%s",
                processing_run_id,
                user_id,
                entry_id,
                idempotency_key,
            )
            return result
        except Exception as exc:
            self.db.rollback()
            error_code = (
                exc.error_code
                if isinstance(exc, PipelineStepError)
                else "PIPELINE_EXCEPTION"
            )
            self._record_failure(
                job_id=job.id,
                user_id=user_id,
                entry_id=entry_id,
                key=idempotency_key,
                processing_run_id=processing_run_id,
                error=str(exc),
                error_code=error_code,
            )
            raise

    def _run_steps(
        self, *, entry_id: str, user_id: str, processing_run_id: str
    ) -> dict[str, Any]:
        run_started = _now_utc()
        steps: dict[str, Any] = {}
        degraded_codes: list[str] = []

        def run_step(
            *,
            step_name: str,
            step_input: dict[str, Any],
            fn: Callable[[], dict[str, Any]],
            error_code: str,
            allow_degraded: bool = False,
            degraded_builder: Callable[[Exception], dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            started = time.perf_counter()
            started_at = _now_utc()
            record: dict[str, Any] = {
                "status": "failed",
                "input": step_input,
                "output": {},
                "error_code": error_code,
            }
            try:
                output = fn()
                status = "completed"
                record = {
                    "status": status,
                    "input": step_input,
                    "output": output,
                    "error_code": None,
                }
                return output
            except Exception as exc:
                if not allow_degraded:
                    raise PipelineStepError(step_name, error_code, str(exc)) from exc
                degraded_codes.append(error_code)
                output = degraded_builder(exc) if degraded_builder else {}
                record = {
                    "status": "degraded",
                    "input": step_input,
                    "output": output,
                    "error_code": error_code,
                    "error": str(exc),
                }
                return output
            finally:
                duration_ms = int((time.perf_counter() - started) * 1000)
                record["duration_ms"] = duration_ms
                record["started_at"] = _iso8601z(started_at)
                steps[step_name] = record
                logger.info(
                    "pipeline step run=%s step=%s status=%s duration_ms=%s",
                    processing_run_id,
                    step_name,
                    record["status"],
                    duration_ms,
                )

        entry = self._get_entry(user_id=user_id, entry_id=entry_id)
        if entry is None:
            raise PipelineStepError(
                "step_01_validate_input",
                "STEP_01_INVALID_INPUT",
                f"journal entry {entry_id} for user {user_id} not found",
            )

        run_step(
            step_name="step_01_validate_input",
            step_input={"entry_id": entry_id, "user_id": user_id},
            error_code="STEP_01_INVALID_INPUT",
            fn=lambda: {
                "entry_status": entry.status,
                "entry_type": entry.entry_type,
                "entry_id": entry.id,
            },
        )

        run_step(
            step_name="step_02_load_entry",
            step_input={"entry_id": entry_id},
            error_code="STEP_02_LOAD_ENTRY",
            fn=lambda: {
                "entry_status": entry.status,
                "entry_type": entry.entry_type,
                "content_length": len(entry.content or ""),
            },
        )

        normalized = run_step(
            step_name="step_03_normalize_text",
            step_input={"content_length": len(entry.content or "")},
            error_code="STEP_03_NORMALIZE",
            fn=lambda: self._step_normalize_text(entry.content or ""),
        )

        ollama_health = run_step(
            step_name="step_04_ollama_health",
            step_input={"model": getattr(self.ollama, "model", "unknown")},
            error_code="STEP_04_OLLAMA_HEALTH",
            allow_degraded=True,
            degraded_builder=lambda exc: {
                "connected": False,
                "model_available": False,
                "models": [],
                "error": str(exc),
            },
            fn=lambda: self.ollama.health(),
        )

        embedding = run_step(
            step_name="step_05_embedding",
            step_input={
                "cache_key": f"embedding:{entry_id}",
                "ollama_connected": bool(ollama_health.get("connected")),
            },
            error_code="STEP_05_EMBEDDING",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "vector": [0.0] * 8,
                "from_cache": False,
                "fallback": True,
            },
            fn=lambda: self._step_embedding(
                entry_id=entry_id,
                normalized_text=normalized["canonical_text"],
                ollama_health=ollama_health,
            ),
        )

        rag = run_step(
            step_name="step_06_rag_search",
            step_input={"embedding_dims": len(embedding.get("vector", []))},
            error_code="STEP_06_RAG_SEARCH",
            allow_degraded=True,
            degraded_builder=lambda exc: {
                "hits": [],
                "hit_count": 0,
                "fallback": True,
                "error": str(exc),
            },
            fn=lambda: self._step_rag_search(embedding.get("vector", [])),
        )

        detection = run_step(
            step_name="step_07_detect_signals",
            step_input={
                "canonical_text_length": len(normalized["canonical_text"]),
                "rag_hit_count": rag.get("hit_count", 0),
            },
            error_code="STEP_07_SIGNAL_DETECTION",
            fn=lambda: self._step_detect_signals(
                user_id=user_id, canonical_text=normalized["canonical_text"]
            ),
        )

        structured = run_step(
            step_name="step_08_upsert_structured",
            step_input={
                "detected_skills": detection["detected_skills"],
                "detected_activities": detection["detected_activities"],
            },
            error_code="STEP_08_STRUCTURED_PERSIST",
            fn=lambda: self._step_upsert_structured(
                user_id=user_id,
                entry_id=entry_id,
                canonical_text=normalized["canonical_text"],
                detection=detection,
            ),
        )

        matched = run_step(
            step_name="step_09_match_quests",
            step_input={
                "detected_skills": detection["detected_skills"],
                "detected_activities": detection["detected_activities"],
            },
            error_code="STEP_09_QUEST_MATCH",
            fn=lambda: self._step_match_quests(
                entry=entry,
                user_id=user_id,
                detected_skills=detection["detected_skills"],
                detected_activities=detection["detected_activities"],
            ),
        )

        progress = run_step(
            step_name="step_10_update_quest_progress",
            step_input={"matched_count": len(matched["matched_quest_ids"])},
            error_code="STEP_10_QUEST_PROGRESS",
            fn=lambda: self._step_update_quest_progress(
                entry=entry,
                user_id=user_id,
                matched_quest_ids=matched["matched_quest_ids"],
            ),
        )

        quest_rewards = run_step(
            step_name="step_11_compute_quest_rewards",
            step_input={
                "completed_quest_ids": progress["completed_quest_ids"],
                "matched_quest_count": len(matched["matched_quest_ids"]),
            },
            error_code="STEP_11_QUEST_REWARDS",
            fn=lambda: self._step_compute_quest_rewards(
                completed_quests=progress["completed_quest_payloads"]
            ),
        )

        skill_awards = run_step(
            step_name="step_12_persist_skill_awards",
            step_input={"quest_rewards": quest_rewards["rewards"]},
            error_code="STEP_12_SKILL_AWARD_PERSIST",
            fn=lambda: self._step_persist_skill_awards(
                user_id=user_id,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                rewards=quest_rewards["rewards"],
            ),
        )

        theme_awards = run_step(
            step_name="step_13_persist_theme_awards",
            step_input={"skill_award_count": len(skill_awards["skill_awards"])},
            error_code="STEP_13_THEME_AWARD_PERSIST",
            fn=lambda: self._step_persist_theme_awards(
                user_id=user_id,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                skill_awards=skill_awards["skill_awards"],
            ),
        )

        run_step(
            step_name="step_14_update_progression_counters",
            step_input={
                "skill_award_count": len(skill_awards["skill_awards"]),
                "theme_award_count": len(theme_awards["theme_awards"]),
            },
            error_code="STEP_14_COUNTER_UPDATES",
            fn=lambda: self._step_update_progression_counters(
                skill_awards=skill_awards["skill_awards"],
                theme_awards=theme_awards["theme_awards"],
            ),
        )

        summary = run_step(
            step_name="step_15_build_summary",
            step_input={
                "structured_id": structured["structured_id"],
                "rag_hit_count": rag.get("hit_count", 0),
            },
            error_code="STEP_15_BUILD_SUMMARY",
            fn=lambda: self._step_build_summary(
                rag_hits=rag.get("hits", []),
                detection=detection,
                progress=progress,
                skill_awards=skill_awards,
                theme_awards=theme_awards,
            ),
        )

        run_step(
            step_name="step_16_mark_entry_completed",
            step_input={"entry_id": entry_id},
            error_code="STEP_16_ENTRY_FINALIZE",
            fn=lambda: self._step_mark_entry_completed(
                entry=entry,
                run_started=run_started,
            ),
        )

        pipeline_meta = run_step(
            step_name="step_17_finalize_payload",
            step_input={"degraded_codes": degraded_codes},
            error_code="STEP_17_FINALIZE_PAYLOAD",
            fn=lambda: {
                "pipeline_version": PIPELINE_VERSION,
                "ruleset_version": RULESET_VERSION,
                "degraded": bool(degraded_codes),
                "degraded_codes": sorted(degraded_codes),
            },
        )

        return {
            "entry_id": entry_id,
            "user_id": user_id,
            "processing_run_id": processing_run_id,
            "status": "completed",
            "completed_at": _iso8601z(_now_utc()),
            "steps": steps,
            "summary": summary,
            "meta": pipeline_meta,
        }

    def _step_normalize_text(self, text: str) -> dict[str, Any]:
        canonical = " ".join((text or "").strip().split())
        return {
            "canonical_text": canonical,
            "char_count": len(canonical),
            "word_count": len(canonical.split()),
        }

    def _step_embedding(
        self,
        *,
        entry_id: str,
        normalized_text: str,
        ollama_health: dict[str, Any],
    ) -> dict[str, Any]:
        cache_key = f"embedding:{entry_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return {"vector": cached, "from_cache": True, "fallback": False}

        if not ollama_health.get("connected"):
            raise RuntimeError("ollama unavailable")

        vector = self.ollama.embed(normalized_text[:4000] or f"entry:{entry_id}")

        self.cache.set(cache_key, vector)
        return {
            "vector": vector,
            "from_cache": False,
            "fallback": not bool(ollama_health.get("connected")),
        }

    def _step_rag_search(self, vector: list[float]) -> dict[str, Any]:
        if not vector:
            return {"hits": [], "hit_count": 0, "fallback": True}
        self.qdrant.ensure_collection()
        hits = self.qdrant.search(vector, limit=5)
        return {"hits": hits, "hit_count": len(hits), "fallback": False}

    def _step_detect_signals(
        self, *, user_id: str, canonical_text: str
    ) -> dict[str, Any]:
        lowered = canonical_text.lower()
        words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_\-']*", lowered))

        skills = self.db.query(Skill).filter(Skill.user_id == user_id).all()
        detected_skills: list[str] = []
        for skill in skills:
            tokens = set(skill.canonical_name.lower().split())
            if tokens and tokens.intersection(words):
                detected_skills.append(skill.name)

        activity_keywords = [
            "run",
            "study",
            "code",
            "write",
            "read",
            "workout",
            "meditate",
            "walk",
            "practice",
            "build",
        ]
        detected_activities = sorted([kw for kw in activity_keywords if kw in lowered])

        emotions = []
        for emotion in ["happy", "sad", "angry", "anxious", "calm", "excited"]:
            if emotion in lowered:
                emotions.append(emotion)

        if "exhausted" in lowered or "drained" in lowered:
            energy_level = 3
        elif "energized" in lowered or "great" in lowered:
            energy_level = 8
        else:
            energy_level = 5

        self_compassion_score = 3 if "hate myself" in lowered else 7

        task_type = "analytical"
        if any(token in lowered for token in ["draw", "paint", "design", "compose"]):
            task_type = "creative"
        elif any(token in lowered for token in ["run", "lift", "swim", "walk"]):
            task_type = "physical"
        elif any(token in lowered for token in ["talk", "friend", "team", "meeting"]):
            task_type = "social"

        return {
            "detected_skills": sorted(set(detected_skills)),
            "detected_activities": detected_activities,
            "dominant_emotions": emotions,
            "energy_level": energy_level,
            "self_compassion_score": self_compassion_score,
            "task_type": task_type,
        }

    def _step_upsert_structured(
        self,
        *,
        user_id: str,
        entry_id: str,
        canonical_text: str,
        detection: dict[str, Any],
    ) -> dict[str, Any]:
        row = (
            self.db.query(JournalEntryStructured)
            .filter(
                JournalEntryStructured.user_id == user_id,
                JournalEntryStructured.entry_id == entry_id,
            )
            .one_or_none()
        )
        if row is None:
            row = JournalEntryStructured(user_id=user_id, entry_id=entry_id)
            self.db.add(row)

        row.canonical_text = canonical_text
        row.primary_action_type = (
            detection["detected_activities"][0]
            if detection["detected_activities"]
            else None
        )
        row.goal_relation = None
        row.time_of_day_bucket = None
        row.dominant_emotions = json.dumps(detection["dominant_emotions"])
        row.energy_level = int(detection["energy_level"])
        row.self_compassion_score = int(detection["self_compassion_score"])
        row.task_type = detection["task_type"]
        row.success_quality = None
        row.blockers_or_obstacles = None
        row.support_used = None
        row.delay_from_planned_time_minutes = None
        row.reflection_depth = None
        row.skills_themes_involved = json.dumps(detection["detected_skills"])
        row.categories = None
        row.sentiment_score = None
        row.safety_flags = None

        self.db.flush()
        return {"structured_id": row.id}

    def _step_match_quests(
        self,
        *,
        entry: JournalEntry,
        user_id: str,
        detected_skills: list[str],
        detected_activities: list[str],
    ) -> dict[str, Any]:
        matched = match_quests(
            entry=entry,
            user_id=user_id,
            detected_skills=detected_skills,
            detected_activities=detected_activities,
            db=self.db,
        )
        return {
            "matched_quest_ids": [q.id for q in matched],
        }

    def _step_update_quest_progress(
        self,
        *,
        entry: JournalEntry,
        user_id: str,
        matched_quest_ids: list[str],
    ) -> dict[str, Any]:
        matched_quests = self._load_quests_by_ids(
            user_id=user_id, quest_ids=matched_quest_ids
        )
        completed_quest_payloads = []
        completed_ids: list[str] = []

        for quest in matched_quests:
            increment = 1
            if quest.completion_type == "cumulative":
                increment = max(1, len((entry.content or "").split()) // 50)

            quest.current_progress = int(quest.current_progress or 0) + increment
            quest.updated_at_utc_ms = int(_now_utc().timestamp() * 1000)

            qp = (
                self.db.query(QuestProgress)
                .filter(
                    QuestProgress.user_id == user_id,
                    QuestProgress.quest_id == quest.id,
                )
                .one_or_none()
            )
            if qp is None:
                qp = QuestProgress(user_id=user_id, quest_id=quest.id)
                self.db.add(qp)

            qp.progress_value = int(quest.current_progress)
            if quest.completion_type == "streak":
                qp.streak_current = max(1, qp.streak_current + 1)
                qp.streak_best = max(qp.streak_best, qp.streak_current)
            qp.last_progress_date = _now_utc().strftime("%Y-%m-%d")

            if quest.current_progress >= int(quest.required_progress or 1):
                quest.status = "completed"
                quest.completed_at = _now_utc()
                quest.completed_at_utc_ms = int(quest.completed_at.timestamp() * 1000)
                completed_quest_payloads.append(
                    {
                        "quest_id": quest.id,
                        "skill_id": quest.skill_id,
                        "base_xp": int(quest.base_xp or 480),
                    }
                )
                completed_ids.append(quest.id)

        self.db.flush()
        return {
            "completed_quest_payloads": completed_quest_payloads,
            "completed_quest_ids": completed_ids,
            "matched_quest_count": len(matched_quests),
        }

    def _load_quests_by_ids(self, *, user_id: str, quest_ids: list[str]) -> list[Any]:
        if not quest_ids:
            return []
        return (
            self.db.query(Quest)
            .filter(Quest.user_id == user_id, Quest.id.in_(quest_ids))
            .all()
        )

    def _step_compute_quest_rewards(
        self, *, completed_quests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        rewards = []
        for quest in completed_quests:
            breakdown = finalize_quest_xp(
                quest_xp_total=int(quest["base_xp"]),
                troll_bp=10000,
                variety_multiplier_bp=10000,
                arc_reward_multiplier_bp=10000,
                penalty_xp=0,
            )
            rewards.append(
                {
                    "quest_id": quest["quest_id"],
                    "skill_id": quest["skill_id"],
                    "quest_xp": breakdown["final_xp"],
                }
            )
        return {"rewards": rewards}

    def _step_persist_skill_awards(
        self,
        *,
        user_id: str,
        entry_id: str,
        processing_run_id: str,
        rewards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        persisted = []
        for reward in rewards:
            identity_key = build_skill_award_identity_key(
                user_id=user_id,
                entry_id=entry_id,
                quest_id=reward["quest_id"],
                xp_reason="quest_complete",
                distribution_type="primary",
                skill_id=reward["skill_id"],
                ruleset_version=RULESET_VERSION,
            )
            existing = (
                self.db.query(XpAward)
                .filter(
                    XpAward.user_id == user_id,
                    XpAward.award_identity_key == identity_key,
                )
                .one_or_none()
            )
            if existing is not None:
                persisted.append(
                    {
                        "award_id": existing.id,
                        "skill_id": existing.skill_id,
                        "quest_id": existing.quest_id,
                        "amount": existing.amount,
                        "identity_key": identity_key,
                        "replayed": True,
                    }
                )
                continue

            row = XpAward(
                user_id=user_id,
                entry_id=entry_id,
                xp_reason="quest_complete",
                processing_run_id=processing_run_id,
                award_identity_key=identity_key,
                ruleset_version=RULESET_VERSION,
                pipeline_version=PIPELINE_VERSION,
                skill_id=reward["skill_id"],
                theme_id=None,
                quest_id=reward["quest_id"],
                amount=int(reward["quest_xp"]),
                distribution_type="primary",
                skill_weight=1.0,
                source_skill_id=None,
                source_skill_xp=None,
            )
            self.db.add(row)
            self.db.flush()
            persisted.append(
                {
                    "award_id": row.id,
                    "skill_id": row.skill_id,
                    "quest_id": row.quest_id,
                    "amount": row.amount,
                    "identity_key": identity_key,
                    "replayed": False,
                }
            )
        return {"skill_awards": persisted}

    def _step_persist_theme_awards(
        self,
        *,
        user_id: str,
        entry_id: str,
        processing_run_id: str,
        skill_awards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        persisted = []

        for skill_award in skill_awards:
            skill_id = skill_award.get("skill_id")
            if not skill_id:
                continue

            mappings = (
                self.db.query(SkillThemeMapping)
                .filter(
                    SkillThemeMapping.user_id == user_id,
                    SkillThemeMapping.skill_id == skill_id,
                )
                .all()
            )
            if not mappings:
                continue

            bp = int(10000 / len(mappings))
            weights = [(m.theme_id, bp) for m in mappings]
            weights[-1] = (weights[-1][0], 10000 - bp * (len(mappings) - 1))

            derived = derive_theme_awards_from_skill_award(
                # Theme propagation target is intentionally tiny vs. skill XP.
                source_skill_xp=max(1, int(int(skill_award["amount"]) * 0.001)),
                source_skill_id=str(skill_id),
                theme_weights_bp=weights,
            )

            for t_award in derived:
                identity_key = build_theme_award_identity_key(
                    user_id=user_id,
                    entry_id=entry_id,
                    quest_id=skill_award["quest_id"],
                    xp_reason="quest_complete",
                    distribution_type="theme",
                    theme_id=str(t_award["theme_id"]),
                    source_skill_id=str(t_award.get("source_skill_id")),
                    source_skill_xp=int(t_award.get("source_skill_xp") or 0),
                    ruleset_version=RULESET_VERSION,
                )
                existing = (
                    self.db.query(XpAward)
                    .filter(
                        XpAward.user_id == user_id,
                        XpAward.award_identity_key == identity_key,
                    )
                    .one_or_none()
                )
                if existing is not None:
                    persisted.append(
                        {
                            "award_id": existing.id,
                            "theme_id": existing.theme_id,
                            "amount": existing.amount,
                            "identity_key": identity_key,
                            "replayed": True,
                        }
                    )
                    continue

                row = XpAward(
                    user_id=user_id,
                    entry_id=entry_id,
                    xp_reason="quest_complete",
                    processing_run_id=processing_run_id,
                    award_identity_key=identity_key,
                    ruleset_version=RULESET_VERSION,
                    pipeline_version=PIPELINE_VERSION,
                    skill_id=None,
                    theme_id=str(t_award["theme_id"]),
                    quest_id=skill_award["quest_id"],
                    amount=int(t_award["amount"]),
                    distribution_type="theme",
                    skill_weight=None,
                    source_skill_id=str(t_award.get("source_skill_id")),
                    source_skill_xp=int(t_award.get("source_skill_xp") or 0),
                )
                self.db.add(row)
                self.db.flush()

                persisted.append(
                    {
                        "award_id": row.id,
                        "theme_id": row.theme_id,
                        "amount": row.amount,
                        "identity_key": identity_key,
                        "replayed": False,
                    }
                )

        return {"theme_awards": persisted}

    def _step_update_progression_counters(
        self,
        *,
        skill_awards: list[dict[str, Any]],
        theme_awards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        skill_updates = 0
        theme_updates = 0

        for award in skill_awards:
            if award.get("replayed"):
                continue
            skill = (
                self.db.query(Skill).filter(Skill.id == award["skill_id"]).one_or_none()
            )
            if skill is None:
                continue
            skill.xp = int(skill.xp) + int(award["amount"])
            skill.last_activity_at = _now_utc()
            skill_updates += 1

        for award in theme_awards:
            if award.get("replayed"):
                continue
            theme = (
                self.db.query(Theme).filter(Theme.id == award["theme_id"]).one_or_none()
            )
            if theme is None:
                continue
            theme.xp = int(theme.xp) + int(award["amount"])
            theme_updates += 1

        self.db.flush()
        return {"updated_skills": skill_updates, "updated_themes": theme_updates}

    def _step_build_summary(
        self,
        *,
        rag_hits: list[dict[str, Any]],
        detection: dict[str, Any],
        progress: dict[str, Any],
        skill_awards: dict[str, Any],
        theme_awards: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "detected_skills": detection["detected_skills"],
            "detected_activities": detection["detected_activities"],
            "rag_hit_count": len(rag_hits),
            "matched_quest_count": int(progress["matched_quest_count"]),
            "completed_quest_count": len(progress["completed_quest_ids"]),
            "skill_award_count": len(skill_awards["skill_awards"]),
            "theme_award_count": len(theme_awards["theme_awards"]),
        }

    def _step_mark_entry_completed(
        self,
        *,
        entry: JournalEntry,
        run_started: datetime,
    ) -> dict[str, Any]:
        entry.status = "completed"
        entry.processed_at = _now_utc()
        entry.processing_duration_ms = max(
            0,
            int((entry.processed_at - run_started).total_seconds() * 1000),
        )
        entry.error_message = None
        self.db.flush()
        return {
            "entry_status": entry.status,
            "processing_duration_ms": entry.processing_duration_ms,
        }

    def _claim_idempotency(
        self, user_id: str, entry_id: str, key: str, processing_run_id: str
    ) -> None:
        claim = EntryIdempotencyClaim(
            user_id=user_id,
            idempotency_key=key,
            entry_id=entry_id,
            processing_run_id=processing_run_id,
            status="claimed",
        )
        self.db.add(claim)
        self.db.flush()

    def _get_idempotent_replay(self, user_id: str, key: str) -> dict[str, Any] | None:
        claim = (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one_or_none()
        )
        if claim is None:
            return None

        if claim.processing_run_id:
            job = (
                self.db.query(ProcessingJob)
                .filter(
                    ProcessingJob.user_id == user_id,
                    ProcessingJob.processing_run_id == claim.processing_run_id,
                    ProcessingJob.step_name == "entry_pipeline",
                )
                .one_or_none()
            )
            if job and job.result_json:
                payload = json.loads(job.result_json)
                payload["replayed"] = True
                payload["idempotency_key"] = key
                return payload
        return {
            "status": claim.status,
            "idempotency_key": key,
            "replayed": True,
            "processing_run_id": claim.processing_run_id,
        }

    def _upsert_job(
        self, user_id: str, entry_id: str, processing_run_id: str
    ) -> ProcessingJob:
        job = ProcessingJob(
            user_id=user_id,
            entry_id=entry_id,
            step_name="entry_pipeline",
            processing_run_id=processing_run_id,
            status="processing",
        )
        self.db.add(job)
        self.db.flush()
        return job

    def _create_attempt(
        self,
        processing_job_id: str,
        attempt_number: int,
        *,
        status: str,
        error_code: str | None = None,
    ) -> None:
        self.db.add(
            ProcessingJobAttempt(
                processing_job_id=processing_job_id,
                attempt_number=attempt_number,
                status=status,
                error_code=error_code,
            )
        )
        self.db.flush()

    def _mark_claim_completed(self, user_id: str, key: str) -> None:
        claim = (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one()
        )
        claim.status = "completed"

    def _record_failure(
        self,
        *,
        job_id: str,
        user_id: str,
        entry_id: str,
        key: str,
        processing_run_id: str,
        error: str,
        error_code: str,
    ) -> None:
        job = (
            self.db.query(ProcessingJob)
            .filter(ProcessingJob.id == job_id)
            .one_or_none()
        )
        if job is not None:
            job.status = "failed"
            job.last_error_code = error_code
            self.db.add(job)
            self._create_attempt(job.id, 2, status="failed", error_code=error_code)

        claim = (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one_or_none()
        )
        if claim is None:
            claim = EntryIdempotencyClaim(
                user_id=user_id,
                idempotency_key=key,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                status="failed",
            )
            self.db.add(claim)
        else:
            claim.status = "failed"

        entry = self._get_entry(user_id=user_id, entry_id=entry_id)
        if entry is not None:
            entry.status = "failed"
            entry.error_message = error
            entry.processed_at = _now_utc()

        self._emit_outbox_event(
            user_id=user_id,
            event_type="entry.processing_failed",
            payload={
                "error": error,
                "error_code": error_code,
                "job_id": job_id,
                "processing_run_id": processing_run_id,
            },
        )
        self.db.commit()

    def _emit_outbox_event(
        self, *, user_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        dedupe_raw = f"{user_id}:{event_type}:{json.dumps(payload, sort_keys=True)}"
        dedupe = hashlib.sha256(dedupe_raw.encode("utf-8")).hexdigest()

        existing = (
            self.db.query(OutboxEvent)
            .filter(OutboxEvent.event_dedupe_key == dedupe)
            .one_or_none()
        )
        if existing is not None:
            return

        self.db.add(
            OutboxEvent(
                user_id=user_id,
                event_type=event_type,
                event_dedupe_key=dedupe,
                payload_json=json.dumps(payload, sort_keys=True),
                status="pending",
            )
        )
        self.db.flush()

    def _get_entry(self, *, user_id: str, entry_id: str) -> JournalEntry | None:
        return (
            self.db.query(JournalEntry)
            .filter(JournalEntry.user_id == user_id, JournalEntry.id == entry_id)
            .one_or_none()
        )
