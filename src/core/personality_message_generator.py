"""
Personality message generation.

Implements Section 3.4 (Message Templates) from architecture.

CRITICAL: ALL user-facing LLM-generated content goes through this service.
Observer is default/fallback for any generation.
"""
import json
import random
import re
from typing import Any, Dict, List, Optional

from src.ai.ollama import OllamaClient
from src.core.personality_memory import PersonalityMemoryService
from src.core.personality_rag import PersonalityRAGService

# Personality color coding (Section 3.4.2)
PERSONALITY_COLORS: Dict[str, str] = {
    "observer":  "text-cyan-500",
    "therapist": "text-blue-500",
    "coach":     "text-orange-500",
    "sassy":     "text-pink-500",
    "wargod":    "text-amber-500",
    "raphael":   "text-purple-500",
}


def _valid_citation(citation: Any) -> bool:
    return isinstance(citation, dict) and bool(
        citation.get("doc_id") or citation.get("title") or citation.get("chunk_id")
    )


class PersonalityMessageGenerator:
    """
    Generate personality messages with templates and RAG.

    CRITICAL: This is the ONLY way to generate user-facing AI content.
    Observer is always the fallback when an unknown personality is requested.
    """

    def __init__(
        self,
        rag_service: PersonalityRAGService,
        memory_service: PersonalityMemoryService,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.rag = rag_service
        self.memory = memory_service
        self.ollama = ollama_client or OllamaClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_entry_feedback(
        self,
        user_id: str,
        entry_id: str,
        entry_text: str,
        personality: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        *,
        extend_thread: bool = True,
    ) -> str:
        """
        Generate journal entry feedback.

        Called for EVERY journal entry. Uses RAG context + memory +
        personality template. Falls back to observer for unknown personalities.
        """
        plan = self.plan_entry_feedback(
            user_id=user_id,
            entry_id=entry_id,
            entry_text=entry_text,
            personality=personality,
            user_state=user_state,
            safety_result=safety_result,
            extend_thread=extend_thread,
        )
        return str(plan["message"])

    def plan_entry_feedback(
        self,
        user_id: str,
        entry_id: str,
        entry_text: str,
        personality: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        *,
        extend_thread: bool = True,
    ) -> Dict[str, Any]:
        """Plan journal entry feedback with generation provenance."""
        rag_context = self.rag.retrieve_relevant_context(
            query_text=entry_text,
            user_id=user_id,
            personality=personality,
            limit=3,
        )
        # Extend thread TTL on each new turn
        if extend_thread:
            self.memory.extend_thread_ttl(user_id)

        if personality == "therapist":
            return self._plan_therapist_feedback(
                entry_text,
                user_state,
                safety_result,
                rag_context,
            )
        if personality == "raphael":
            return self._plan_raphael_feedback(entry_text, user_state, rag_context)

        dispatch = {
            "observer": lambda: self._template_payload(
                self._generate_observer_feedback(entry_text, user_state, rag_context),
                template_key="observer.entry_feedback",
            ),
            "coach": lambda: self._template_payload(
                self._generate_coach_feedback(entry_text, user_state, rag_context),
                template_key="coach.entry_feedback",
            ),
            "sassy": lambda: self._template_payload(
                self._generate_sassy_feedback(entry_text, user_state, rag_context),
                template_key="sassy.entry_feedback",
            ),
            "wargod": lambda: self._template_payload(
                self._generate_wargod_feedback(entry_text, user_state, rag_context),
                template_key="wargod.entry_feedback",
            ),
        }
        return dispatch.get(
            personality,
            lambda: self._template_payload(
                self._generate_observer_feedback(entry_text, user_state, rag_context),
                template_key="observer.entry_feedback",
            ),
        )()

    def generate_quest_description(
        self,
        user_id: str,
        quest_template: Dict[str, Any],
        personality: str,
        user_state: Dict[str, Any],
    ) -> str:
        """
        Generate quest description / narrative in personality voice.

        CRITICAL: Quest content MUST go through this method.
        """
        base = quest_template.get("description", "")

        dispatch = {
            "observer":  f"[OBS] {base}",
            "therapist": f"[THE] 💙 A journey worth taking: {base}",
            "coach":     f"[COACH] Let's tackle this: {base}",
            "sassy":     f"[SASSY] Oh darling, time to slay this quest: {base} ✨",
            "wargod":    f"[WARGOD] ⚔️ EPIC QUEST UNLOCKED: {base}",
            "raphael":   f"[RAPHAEL] 🌙 The path unfolds before you: {base}",
        }
        return dispatch.get(personality, f"[OBS] {base}")

    def generate_insight_summary(
        self,
        user_id: str,
        insight_data: Dict[str, Any],
        personality: str,
    ) -> str:
        """
        Generate insight summary in personality voice.

        CRITICAL: Insight text MUST go through this method.
        """
        raw = insight_data.get("raw_text", "")

        dispatch = {
            "observer":  f"[OBS] Pattern detected: {raw}",
            "therapist": f"[THE] 💙 {raw}",
            "coach":     f"[COACH] Here's what your data says: {raw}",
            "sassy":     f"[SASSY] Spilling the tea on your patterns, love: {raw} ☕",
            "wargod":    f"[WARGOD] ⚔️ INTELLIGENCE GATHERED: {raw}",
            "raphael":   f"[RAPHAEL] 🌙 {raw}",
        }
        return dispatch.get(personality, f"[OBS] Pattern detected: {raw}")

    def generate_achievement_notification(
        self,
        user_id: str,
        achievement: Dict[str, Any],
        personality: str,
    ) -> str:
        """Generate achievement / level-up notification in personality voice."""
        title = achievement.get("title", "Achievement unlocked")

        dispatch = {
            "observer":  f"[OBS] Achievement recorded: {title}.",
            "therapist": f"[THE] 💙 You earned this — {title}. Be proud of yourself.",
            "coach":     f"[COACH] YES! {title} — you absolutely earned that! 🎯",
            "sassy":     f"[SASSY] Oh look at you, absolutely smashing it: {title}! 💅",
            "wargod":    f"[WARGOD] ⚔️ GLORY! {title} — YOUR LEGEND GROWS!",
            "raphael":   f"[RAPHAEL] 🌙 {title} — a milestone on the infinite path.",
        }
        return dispatch.get(personality, f"[OBS] Achievement recorded: {title}.")

    def generate_safety_intervention(
        self,
        user_id: str,
        entry_text: str,
        safety_result: Dict[str, Any],
        country: str = "FR",
    ) -> str:
        """
        Generate safety intervention message.

        ALWAYS uses therapist personality regardless of active personality.
        Includes localized crisis resources from RAG.
        Returns empty string when no intervention is needed.
        """
        risk_level = safety_result.get("risk_level", "none")

        if risk_level == "none":
            return ""

        if risk_level == "warning":
            return (
                "[THE] 💙 I want to check in — it sounds like you're going through "
                "something difficult. Remember that support is available if you need it."
            )

        # crisis level
        resources = self.rag.retrieve_safety_resources(user_id, country)
        message = (
            "[THE] 💙 I'm really concerned about what you've shared. "
            "Your safety is the most important thing right now."
        )

        if resources:
            message += "\n\nImmediate support resources:\n"
            for r in resources[:3]:
                message += f"- {r['content']}\n"

        message += "\nPlease reach out to someone you trust or one of these resources."
        return message

    # ------------------------------------------------------------------
    # Personality-specific templates (Section 3.4.1)
    # ------------------------------------------------------------------

    def _generate_observer_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> str:
        """Observer: neutral, factual, analytical."""
        templates = [
            "[OBS] Entry recorded. Processing complete.",
            "[OBS] Noted. Your approach shows {skill_count} distinct skill application(s).",
            "[OBS] Entry processed. Anomaly score: {anomaly_score}/10.",
        ]
        return random.choice(templates).format(
            skill_count=len(user_state.get("skills", [])),
            anomaly_score=round(user_state.get("anomaly_score", 0.0), 1),
        )

    def _generate_therapist_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> str:
        """Therapist: empathetic, validating."""
        sentiment = safety_result.get("sentiment_score", 50)

        if sentiment < 40:
            return "[THE] 💙 I hear that you're struggling. That sounds really difficult. Your feelings are valid."
        if sentiment > 70:
            return "[THE] 💙 It's wonderful to see you're feeling positive. Keep nurturing that energy."
        return "[THE] 💙 Thank you for sharing. I'm here to support you through this."

    def _generate_coach_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> str:
        """Coach: motivating, goal-oriented."""
        templates = [
            "[COACH] Great work! You're building momentum. Keep pushing forward!",
            "[COACH] Nice! You just levelled up {skill_count} skill(s). That's real progress!",
            "[COACH] Strong effort! Your consistency is paying off. Don't stop now!",
        ]
        return random.choice(templates).format(
            skill_count=len(user_state.get("skills", []))
        )

    def _generate_sassy_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> str:
        """Sassy Queen: playful, challenging, British wit."""
        templates = [
            "[SASSY] Oh bloody hell, look at you actually putting in effort. Colour me impressed, darling. 💅",
            "[SASSY] Not bad at all, love — though I've seen better. Just kidding, you're doing brilliantly. ✨",
            "[SASSY] Well well well, {skill_count} skill(s) and you're still going? Absolutely cheeky. Keep it up! 😏",
            "[SASSY] Crikey, someone's been productive! Don't let it go to your head, sweetheart. 🫖",
        ]
        return random.choice(templates).format(
            skill_count=len(user_state.get("skills", []))
        )

    def _generate_wargod_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> str:
        """Wargod: epic, triumphant, intense."""
        templates = [
            "[WARGOD] ⚔️ LEGENDARY! You have achieved GLORY this day! The chronicles will remember this triumph!",
            "[WARGOD] ⚔️ THE BATTLEFIELD IS YOURS! {skill_count} skill(s) forged in fire — UNSTOPPABLE!",
            "[WARGOD] ⚔️ WARRIOR! Each entry is a battle won. The war is far from over — ONWARD!",
        ]
        return random.choice(templates).format(
            skill_count=len(user_state.get("skills", []))
        )

    def _generate_raphael_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> str:
        """Raphael: philosophical, reflective, deep."""
        templates = [
            "[RAPHAEL] 🌙 Every journey inward reveals new landscapes of the self.",
            "[RAPHAEL] 🌙 Growth emerges not from the destination, but from the courage to continue.",
            "[RAPHAEL] 🌙 In your struggle, I see the seeds of transformation.",
            "[RAPHAEL] 🌙 The observer within you grows wiser with each word written.",
        ]
        return random.choice(templates)

    def _template_payload(
        self,
        message: str,
        *,
        template_key: str,
    ) -> Dict[str, Any]:
        return {
            "message": message,
            "generation_mode": "template",
            "citations": [],
            "fallback_reason": None,
            "template_key": template_key,
        }

    def _safe_fallback_payload(
        self,
        *,
        personality: str,
        fallback_reason: str,
    ) -> Dict[str, Any]:
        if personality == "therapist":
            message = (
                "[THE] 💙 I may be missing context and I cannot verify sources right now. "
                "Take one gentle next step, keep the bar low, and reach out for support if things feel heavy."
            )
        else:
            message = (
                "[RAPHAEL] 🌙 I may be missing context and I cannot verify sources right now. "
                "Stay with the smallest honest next step, and let clarity grow from action."
            )
        return {
            "message": message,
            "generation_mode": "safe_fallback",
            "citations": [],
            "fallback_reason": fallback_reason,
            "template_key": f"{personality}.safe_fallback",
        }

    def _llm_feedback_payload(
        self,
        *,
        personality: str,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        evidence_block = "\n".join(
            f"- {item.get('content', '').strip()}"
            for item in rag_context[:3]
            if item.get("content")
        )
        system = (
            "Return JSON only with a single key: message. "
            "Keep it under 60 words, supportive, specific, and grounded in the provided evidence."
        )
        prompt = (
            f"You are writing as {personality}.\n\n"
            f"User entry:\n{entry_text}\n\n"
            f"User state:\n{json.dumps(user_state, sort_keys=True)}\n\n"
            f"Evidence:\n{evidence_block}"
        )
        raw = self.ollama.generate_json(prompt, system=system)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.get("response", "").strip())
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        parsed = json.loads(cleaned or "{}")
        message = str(parsed.get("message", "")).strip()
        if not message:
            raise ValueError("missing message in llm personality response")
        return {
            "message": message[:500],
            "generation_mode": "llm_rag",
            "citations": [
                item.get("citation")
                for item in rag_context[:3]
                if isinstance(item, dict) and _valid_citation(item.get("citation"))
            ],
            "fallback_reason": None,
            "template_key": None,
        }

    def _plan_therapist_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        safety_result: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        citations = [
            item.get("citation")
            for item in rag_context[:3]
            if isinstance(item, dict) and _valid_citation(item.get("citation"))
        ]
        if not citations:
            return self._safe_fallback_payload(
                personality="therapist",
                fallback_reason="DEPENDENCY_QDRANT_UNAVAILABLE_OR_EMPTY",
            )
        try:
            return self._llm_feedback_payload(
                personality="therapist",
                entry_text=entry_text,
                user_state={**user_state, "safety": safety_result},
                rag_context=rag_context,
            )
        except Exception:
            return self._safe_fallback_payload(
                personality="therapist",
                fallback_reason="DEPENDENCY_OLLAMA_UNAVAILABLE",
            )

    def _plan_raphael_feedback(
        self,
        entry_text: str,
        user_state: Dict[str, Any],
        rag_context: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        citations = [
            item.get("citation")
            for item in rag_context[:3]
            if isinstance(item, dict) and _valid_citation(item.get("citation"))
        ]
        if not citations:
            return self._safe_fallback_payload(
                personality="raphael",
                fallback_reason="DEPENDENCY_QDRANT_UNAVAILABLE_OR_EMPTY",
            )
        try:
            return self._llm_feedback_payload(
                personality="raphael",
                entry_text=entry_text,
                user_state=user_state,
                rag_context=rag_context,
            )
        except Exception:
            return self._safe_fallback_payload(
                personality="raphael",
                fallback_reason="DEPENDENCY_OLLAMA_UNAVAILABLE",
            )
