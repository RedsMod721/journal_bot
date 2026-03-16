"""
Personality orchestration for journal processing.

Integrates personality selection and message generation into the pipeline.
Implements Section 3 (Personality System) from COMPLETE_ARCHITECTURE.md.

CRITICAL: EVERY journal entry MUST produce a personality message.
This is the sole channel for AI feedback to the user.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.core.personality_memory import PersonalityMemoryService
from src.core.personality_message_generator import PersonalityMessageGenerator
from src.core.personality_message_persistence import MessagePersistenceService
from src.core.personality_rag import PersonalityRAGService
from src.core.personality_selection import PersonalitySelector, SELECTOR_VERSION
from src.core.personality_state_manager import PersonalityStateManager

logger = logging.getLogger(__name__)

PROMPT_VERSION = "personality_v3.2"
BEHAVIORAL_INTENT_VERSION = "bi_v1.4"


class PersonalityOrchestrator:
    """Orchestrate personality system in journal entry processing.

    Owns the full selection → generation → memory → persistence flow.
    The orchestrator never raises: any internal failure degrades to a
    safe observer message so the enclosing pipeline step can choose
    whether to propagate or swallow the error.
    """

    def __init__(
        self,
        db: Session,
        rag_service: PersonalityRAGService | None = None,
    ) -> None:
        self.db = db
        self.selector = PersonalitySelector(db)
        self.state_manager = PersonalityStateManager(db)
        self.memory_service = PersonalityMemoryService(db)

        try:
            self.rag_service: PersonalityRAGService | None = (
                rag_service or PersonalityRAGService()
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("PersonalityRAGService init failed (RAG disabled): %s", exc)
            self.rag_service = None

        self._rag_proxy = self.rag_service or _NullRAGService()
        self.message_generator = PersonalityMessageGenerator(
            self._rag_proxy, self.memory_service
        )
        self.message_persistence = MessagePersistenceService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_entry_personality(
        self,
        user_id: str,
        entry_id: str,
        entry_text: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        requested_personality: Optional[str] = None,
        now_utc: Optional[datetime] = None,
        pipeline_version: str = "v3.0",
    ) -> Dict[str, Any]:
        """Complete personality processing for a journal entry.

        Steps
        -----
        1. Select personality (deterministic, priority-ordered)
        2. Update personality state (active_personality, last_switched_at, …)
        3. Generate personality message
        4. Store thread memory — user turn
        5. Store thread memory — assistant turn
        6. Extend thread TTL for all active thread memories
        7. Store short-term memory summary
        8. Persist message with exactly-once semantics
        9. Return result dict

        Parameters
        ----------
        user_id:
            UUID of the user.
        entry_id:
            UUID of the journal entry.
        entry_text:
            Raw entry content.
        user_state:
            Snapshot of user metrics consumed by selection logic::

                {
                    "harmony_score":        int,    # 0-100
                    "anomaly_score":        float,
                    "anomaly_contribution": float,
                    "tutorial_active":      bool,
                    "regression_arc_active":bool,
                    "major_achievement":    bool,
                    "skills":               list,   # detected skill dicts
                    "overwork_stage":       int,    # 0-3
                }

        safety_result:
            Output from safety/crisis detection::

                {"force_therapist": bool, "risk_level": str, "sentiment_score": int}

        requested_personality:
            Optional user-requested personality; may be denied by hard gates.
        now_utc:
            Authoritative timestamp for this pipeline run.
        pipeline_version:
            Pinned version string used in deterministic seed generation.

        Returns
        -------
        dict with keys: personality, selection_reason, message, message_id
        """
        now_utc = now_utc or datetime.now(timezone.utc)
        plan = self.plan_entry_personality(
            user_id=user_id,
            entry_id=entry_id,
            entry_text=entry_text,
            user_state=user_state,
            safety_result=safety_result,
            requested_personality=requested_personality,
            now_utc=now_utc,
            pipeline_version=pipeline_version,
        )
        return self.apply_entry_personality_plan(
            user_id=user_id,
            entry_id=entry_id,
            entry_text=entry_text,
            plan=plan,
            now_utc=now_utc,
        )

    def plan_entry_personality(
        self,
        user_id: str,
        entry_id: str,
        entry_text: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        requested_personality: Optional[str] = None,
        now_utc: Optional[datetime] = None,
        pipeline_version: str = "v3.0",
    ) -> Dict[str, Any]:
        """Build the full personality output plan without persisting it."""
        now_utc = now_utc or datetime.now(timezone.utc)

        selected_personality, selection_reason, selection_factors = (
            self.selector.select_personality(
                user_id=user_id,
                entry_id=entry_id,
                entry_text=entry_text,
                user_state=user_state,
                safety_result=safety_result,
                now_utc=now_utc,
                requested_personality=requested_personality,
                pipeline_version=pipeline_version,
            )
        )

        logger.debug(
            "personality selected user=%s entry=%s personality=%s reason=%s",
            user_id,
            entry_id,
            selected_personality,
            selection_reason,
        )

        feedback_plan = self.message_generator.plan_entry_feedback(
            user_id=user_id,
            entry_id=entry_id,
            entry_text=entry_text,
            personality=selected_personality,
            user_state=user_state,
            safety_result=safety_result,
            extend_thread=False,
        )
        message_text = str(feedback_plan["message"])

        citations = list(feedback_plan.get("citations", []))
        seed_material = str(selection_factors.get("seed", ""))
        selector_seed_hash = (
            hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
            if seed_material
            else None
        )

        context_data: Dict[str, Any] = {
            "prompt_version": PROMPT_VERSION,
            "behavioral_intent_version": BEHAVIORAL_INTENT_VERSION,
            "selection_reason": selection_reason,
            "selection_factors": selection_factors,
            "safety": {
                "risk_level": safety_result.get("risk_level", "none"),
                "force_therapist": bool(safety_result.get("force_therapist", False)),
                "matched_rules": safety_result.get("matched_rules", []),
            },
            "citations": citations,
            "generation_mode": feedback_plan.get("generation_mode", "template"),
            "fallback_reason": feedback_plan.get("fallback_reason"),
            "template_key": feedback_plan.get("template_key"),
            "multi_personality": {
                "is_primary": True,
                "impact_multiplier": 1.0,
                "primary_personality": selected_personality,
            },
            "pipeline_version": pipeline_version,
        }
        skill_count = len(user_state.get("skills", []))
        summary = (
            f"Entry processed by {selected_personality}. "
            f"Skills: {skill_count}. "
            f"Harmony: {user_state.get('harmony_score', 0)}."
        )

        return {
            "personality": selected_personality,
            "selection_reason": selection_reason,
            "selection_factors": selection_factors,
            "message": message_text,
            "message_type": "entry_feedback",
            "context_data": context_data,
            "generation_mode": feedback_plan.get("generation_mode", "template"),
            "citations": citations,
            "fallback_reason": feedback_plan.get("fallback_reason"),
            "template_key": feedback_plan.get("template_key"),
            "selector_version": SELECTOR_VERSION,
            "selector_seed_hash": selector_seed_hash,
            "logical_slot_key": "primary",
            "thread_memories": [
                {
                    "role": "user",
                    "content": entry_text,
                },
                {
                    "role": "assistant",
                    "content": message_text,
                    "personality": selected_personality,
                    "message_type": "entry_feedback",
                },
            ],
            "short_term_summary": summary,
            "pipeline_version": pipeline_version,
        }

    def apply_entry_personality_plan(
        self,
        user_id: str,
        entry_id: str,
        entry_text: str,
        plan: Dict[str, Any],
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Persist a previously generated personality plan."""
        del entry_text
        now_utc = now_utc or datetime.now(timezone.utc)
        selected_personality = str(plan["personality"])
        selection_reason = str(plan["selection_reason"])
        selection_factors = dict(plan.get("selection_factors", {}))
        message_text = str(plan["message"])
        stored = self.message_persistence.store_message(
            user_id=user_id,
            entry_id=entry_id,
            personality=selected_personality,
            message_type=str(plan.get("message_type", "entry_feedback")),
            message_text=message_text,
            selector_version=int(plan.get("selector_version", SELECTOR_VERSION)),
            selector_seed_hash=plan.get("selector_seed_hash"),
            logical_slot_key=str(plan.get("logical_slot_key", "primary")),
            context_data=dict(plan.get("context_data", {})),
            now_utc=now_utc,
        )
        message = stored["message"]
        if stored["inserted"]:
            self.state_manager.update_after_selection(
                user_id=user_id,
                selected_personality=selected_personality,
                selection_reason=selection_reason,
                selection_factors=selection_factors,
                now_utc=now_utc,
            )

            for memory in plan.get("thread_memories", []):
                self.memory_service.store_thread_memory(
                    user_id=user_id,
                    entry_id=entry_id,
                    role=memory["role"],
                    content=memory["content"],
                    personality=memory.get("personality"),
                    message_type=memory.get("message_type"),
                    now_utc=now_utc,
                )

            self.memory_service.extend_thread_ttl(user_id, now_utc)
            self.memory_service.store_short_term_memory(
                user_id=user_id,
                entry_id=entry_id,
                summary=str(plan.get("short_term_summary", "")),
                personality=selected_personality,
                now_utc=now_utc,
            )

        return {
            "personality": selected_personality,
            "selection_reason": selection_reason,
            "message": message.message_text,
            "message_id": message.id,
            "context_data": dict(plan.get("context_data", {})),
            "generation_mode": plan.get("generation_mode", "template"),
            "citations": list(plan.get("citations", [])),
            "fallback_reason": plan.get("fallback_reason"),
            "template_key": plan.get("template_key"),
            "inserted": bool(stored["inserted"]),
        }


# ---------------------------------------------------------------------------
# Null RAG service — used when PersonalityRAGService fails to initialise
# ---------------------------------------------------------------------------


class _NullRAGService:
    """Drop-in replacement for PersonalityRAGService when Qdrant is unavailable."""

    def retrieve_relevant_context(self, **_kwargs: Any):  # type: ignore[override]
        return []

    def retrieve_safety_resources(self, **_kwargs: Any):  # type: ignore[override]
        return []
