"""
Personality message persistence.

Stores generated messages with exactly-once semantics using the
uq_personality_messages_exactly_once constraint on (user_id, entry_id,
message_type, personality).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import insert
from sqlalchemy.orm import Session

from src.db.models.personality import PersonalityMessage


class MessagePersistenceService:
    """Persist personality messages with exactly-once semantics."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def store_message(
        self,
        user_id: str,
        entry_id: str,
        personality: str,
        message_type: str,
        message_text: str,
        selector_version: int = 1,
        selector_seed_hash: Optional[str] = None,
        logical_slot_key: str = "default",
        context_data: Optional[Dict[str, Any]] = None,
        quest_id: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Persist a personality message.

        Idempotent by logical slot: if the same selector slot already exists for
        (user_id, entry_id, message_type, logical_slot_key, selector_version),
        the existing row is returned and no state is mutated.
        """
        now_utc = now_utc or datetime.now(timezone.utc)
        context_json = json.dumps(context_data or {}, separators=(",", ":"))
        message_id = str(uuid.uuid4())

        stmt = insert(PersonalityMessage).prefix_with("OR IGNORE").values(
            id=message_id,
            user_id=user_id,
            entry_id=entry_id,
            personality=personality,
            message_type=message_type,
            message_text=message_text,
            selector_version=selector_version,
            selector_seed_hash=selector_seed_hash,
            logical_slot_key=logical_slot_key,
            context_data=context_json,
            quest_id=quest_id,
            created_at=now_utc,
        )
        result = self.db.execute(stmt)
        self.db.flush()

        existing = (
            self.db.query(PersonalityMessage)
            .filter(
                PersonalityMessage.user_id == user_id,
                PersonalityMessage.entry_id == entry_id,
                PersonalityMessage.message_type == message_type,
                PersonalityMessage.logical_slot_key == logical_slot_key,
                PersonalityMessage.selector_version == selector_version,
            )
            .one()
        )
        return {
            "message": existing,
            "inserted": bool(getattr(result, "rowcount", 0)),
        }

    def get_messages_for_entry(
        self,
        user_id: str,
        entry_id: str,
    ) -> list[PersonalityMessage]:
        """Return all persisted messages for a given entry, ordered by creation time."""
        return (
            self.db.query(PersonalityMessage)
            .filter(
                PersonalityMessage.user_id == user_id,
                PersonalityMessage.entry_id == entry_id,
            )
            .order_by(PersonalityMessage.created_at)
            .all()
        )
