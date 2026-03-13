"""Helpers for exposing personality messages through API-friendly shapes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from src.db.models.personality import PersonalityMessage


def _iso8601z(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def parse_context_data(raw_context: str | None) -> dict[str, Any]:
    """Return a safe dict for ``context_data`` regardless of DB contents."""
    if not raw_context:
        return {}
    try:
        parsed = json.loads(raw_context)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_multi_personality(
    *,
    logical_slot_key: str,
    personality: str,
    context_data: dict[str, Any],
) -> dict[str, Any]:
    raw_multi = context_data.get("multi_personality")
    multi = raw_multi if isinstance(raw_multi, dict) else {}

    if "is_primary" in multi:
        is_primary = bool(multi["is_primary"])
    else:
        is_primary = logical_slot_key == "primary"

    impact_multiplier_raw = multi.get("impact_multiplier")
    try:
        impact_multiplier = float(impact_multiplier_raw)
    except (TypeError, ValueError):
        impact_multiplier = 1.0 if is_primary else 0.5

    primary_personality = multi.get("primary_personality")
    if not isinstance(primary_personality, str) or not primary_personality:
        primary_personality = personality

    return {
        "is_primary": is_primary,
        "primary_personality": primary_personality,
        "impact_multiplier": impact_multiplier,
    }


def serialize_personality_message(message: PersonalityMessage) -> dict[str, Any]:
    """Serialize a ``PersonalityMessage`` row with normalized metadata."""
    context_data = parse_context_data(message.context_data)
    return {
        "id": message.id,
        "entry_id": message.entry_id,
        "personality": message.personality,
        "message_type": message.message_type,
        "message_text": message.message_text,
        "logical_slot_key": message.logical_slot_key,
        "context_data": context_data,
        "multi_personality": normalize_multi_personality(
            logical_slot_key=message.logical_slot_key,
            personality=message.personality,
            context_data=context_data,
        ),
        "created_at": _iso8601z(message.created_at),
    }


def serialize_personality_messages(
    messages: Iterable[PersonalityMessage],
) -> list[dict[str, Any]]:
    return [serialize_personality_message(message) for message in messages]
