"""
Personality memory system.

Implements Section 3.5 (Memory System) from architecture.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.db.models.personality import PersonalityMemory, PersonalityState

_ALLOWED_LONG_TERM_SLOTS = frozenset(
    ["safety", "insight", "arc_milestone", "user_bookmark", "preference", "identity"]
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PersonalityMemoryService:
    """Manage three-tier memory system (Section 3.5)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Thread memory (Section 3.5.2)
    # ------------------------------------------------------------------

    def store_thread_memory(
        self,
        user_id: str,
        entry_id: str,
        role: str,
        content: str,
        personality: Optional[str] = None,
        message_type: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> PersonalityMemory:
        """
        Store thread memory (Section 3.5.2).

        Key format:
        - User turn:      thread:{entry_id}:user
        - Assistant turn: thread:{entry_id}:assistant:{message_type}:{personality}

        TTL: 2 hours from now.
        Idempotent: updates content + extends TTL on duplicate key.
        """
        now_utc = now_utc or _utc_now()
        expires_at = now_utc + timedelta(hours=2)

        if role == "user":
            key = f"thread:{entry_id}:user"
        elif role == "assistant":
            if not personality or not message_type:
                raise ValueError("Assistant turns require personality and message_type")
            key = f"thread:{entry_id}:assistant:{message_type}:{personality}"
        else:
            raise ValueError(f"Invalid role: {role!r}. Must be 'user' or 'assistant'")

        context: Dict[str, Any] = {"role": role, "ts": now_utc.isoformat() + "Z"}
        if personality:
            context["personality"] = personality

        context_json = json.dumps(context, separators=(",", ":"))

        existing = (
            self.db.query(PersonalityMemory)
            .filter(
                PersonalityMemory.user_id == user_id,
                PersonalityMemory.tier == "thread",
                PersonalityMemory.key == key,
            )
            .first()
        )

        if existing:
            existing.value = content
            existing.context = context_json
            existing.expires_at = expires_at
            self.db.flush()
            return existing

        memory = PersonalityMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tier="thread",
            key=key,
            value=content,
            context=context_json,
            expires_at=expires_at,
            created_at=now_utc,
        )
        self.db.add(memory)
        self.db.flush()
        return memory

    def extend_thread_ttl(
        self,
        user_id: str,
        now_utc: Optional[datetime] = None,
    ) -> int:
        """
        Extend TTL for all non-expired thread memories to 2 hours from now.

        Called on each new turn to keep the conversation alive.
        Returns count of memories extended.
        """
        now_utc = now_utc or _utc_now()
        new_expires_at = now_utc + timedelta(hours=2)

        memories = (
            self.db.query(PersonalityMemory)
            .filter(
                PersonalityMemory.user_id == user_id,
                PersonalityMemory.tier == "thread",
                PersonalityMemory.expires_at > now_utc,
            )
            .all()
        )

        for memory in memories:
            memory.expires_at = new_expires_at

        self.db.flush()
        return len(memories)

    def get_thread_context(
        self,
        user_id: str,
        now_utc: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return current thread context (non-expired), ordered by created_at.

        Each item: {role, content, personality, ts}
        """
        now_utc = now_utc or _utc_now()

        memories = (
            self.db.query(PersonalityMemory)
            .filter(
                PersonalityMemory.user_id == user_id,
                PersonalityMemory.tier == "thread",
                PersonalityMemory.expires_at > now_utc,
            )
            .order_by(PersonalityMemory.created_at)
            .all()
        )

        result = []
        for m in memories:
            try:
                ctx = json.loads(m.context)
                result.append(
                    {
                        "role": ctx.get("role"),
                        "content": m.value,
                        "personality": ctx.get("personality"),
                        "ts": ctx.get("ts"),
                    }
                )
            except (json.JSONDecodeError, AttributeError):
                pass

        return result

    # ------------------------------------------------------------------
    # Short-term memory (Section 3.5.3)
    # ------------------------------------------------------------------

    def store_short_term_memory(
        self,
        user_id: str,
        entry_id: str,
        summary: str,
        personality: str,
        now_utc: Optional[datetime] = None,
    ) -> PersonalityMemory:
        """
        Store short-term memory (Section 3.5.3).

        Key format: short_term:{entry_id}:summary
        TTL: memory_short_term_days from PersonalityState (default 7).
        Idempotent: updates summary + resets TTL on duplicate key.
        """
        now_utc = now_utc or _utc_now()

        state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        ttl_days = state.memory_short_term_days if state else 7
        expires_at = now_utc + timedelta(days=ttl_days)

        key = f"short_term:{entry_id}:summary"
        context_json = json.dumps(
            {"personality": personality, "created_at": now_utc.isoformat() + "Z"},
            separators=(",", ":"),
        )

        existing = (
            self.db.query(PersonalityMemory)
            .filter(
                PersonalityMemory.user_id == user_id,
                PersonalityMemory.tier == "short_term",
                PersonalityMemory.key == key,
            )
            .first()
        )

        if existing:
            existing.value = summary
            existing.context = context_json
            existing.expires_at = expires_at
            self.db.flush()
            return existing

        memory = PersonalityMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tier="short_term",
            key=key,
            value=summary,
            context=context_json,
            expires_at=expires_at,
            created_at=now_utc,
        )
        self.db.add(memory)
        self.db.flush()
        return memory

    # ------------------------------------------------------------------
    # Long-term memory (Section 3.5.4)
    # ------------------------------------------------------------------

    def store_long_term_pointer(
        self,
        user_id: str,
        memory_qdrant_point_id: str,
        slot: str,
        summary: str,
        personality: str,
        qdrant_collection: str = "user_memory",
        now_utc: Optional[datetime] = None,
    ) -> PersonalityMemory:
        """
        Store long-term memory pointer (Section 3.5.4).

        Key format: long_term:{memory_qdrant_point_id}
        No expiration (permanent).

        Valid slots: safety, insight, arc_milestone, user_bookmark, preference, identity.
        Idempotent: updates summary + context on duplicate key.
        """
        if slot not in _ALLOWED_LONG_TERM_SLOTS:
            raise ValueError(
                f"Invalid slot: {slot!r}. Must be one of {sorted(_ALLOWED_LONG_TERM_SLOTS)}"
            )

        now_utc = now_utc or _utc_now()
        key = f"long_term:{memory_qdrant_point_id}"
        context_json = json.dumps(
            {
                "memory_qdrant_point_id": memory_qdrant_point_id,
                "qdrant_collection": qdrant_collection,
                "slot": slot,
                "personality": personality,
                "created_at": now_utc.isoformat() + "Z",
            },
            separators=(",", ":"),
        )
        # Keep only a short preview in SQLite; full content lives in Qdrant
        value = summary[:200]

        existing = (
            self.db.query(PersonalityMemory)
            .filter(
                PersonalityMemory.user_id == user_id,
                PersonalityMemory.tier == "long_term",
                PersonalityMemory.key == key,
            )
            .first()
        )

        if existing:
            existing.value = value
            existing.context = context_json
            self.db.flush()
            return existing

        memory = PersonalityMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tier="long_term",
            key=key,
            value=value,
            context=context_json,
            expires_at=None,  # permanent
            created_at=now_utc,
        )
        self.db.add(memory)
        self.db.flush()
        return memory

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_expired(self, now_utc: Optional[datetime] = None) -> int:
        """
        Delete all memories whose expires_at has passed.

        Returns count of deleted records.
        """
        now_utc = now_utc or _utc_now()

        expired = (
            self.db.query(PersonalityMemory)
            .filter(
                PersonalityMemory.expires_at.isnot(None),
                PersonalityMemory.expires_at <= now_utc,
            )
            .all()
        )

        count = len(expired)
        for memory in expired:
            self.db.delete(memory)

        self.db.flush()
        return count
