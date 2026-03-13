"""
Personality state management.

Handles personality state updates after selection.
"""
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.personality import PersonalityState
from src.db.models.user import User


class PersonalityStateManager:
    """Manage personality state updates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def update_after_selection(
        self,
        user_id: str,
        selected_personality: str,
        selection_reason: str,
        selection_factors: dict[str, Any],
        now_utc: datetime,
    ) -> PersonalityState:
        """
        Update personality state after selection.

        Rules:
        - Update active_personality
        - Update last_switched_at if personality changed
        - Update last_selection_factors
        - Track wargod usage date in UTC
        """
        state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        if not state:
            state = PersonalityState(user_id=user_id)
            self.db.add(state)

        changed = state.active_personality != selected_personality
        state.active_personality = selected_personality

        if changed:
            state.last_switched_at = now_utc

        prev_factors: dict[str, Any]
        try:
            parsed = json.loads(state.last_selection_factors or "{}")
            prev_factors = parsed if isinstance(parsed, dict) else {}
        except Exception:
            prev_factors = {}

        merged = dict(prev_factors)
        merged.update(selection_factors)

        if selected_personality == "wargod":
            merged["wargod_last_used_date_utc"] = now_utc.date().isoformat()
        elif "wargod_last_used_date_utc" in prev_factors:
            merged["wargod_last_used_date_utc"] = prev_factors["wargod_last_used_date_utc"]

        state.last_selection_factors = json.dumps(merged, separators=(",", ":"))

        user = self.db.query(User).filter(User.id == user_id).first()
        if user is not None:
            user.current_personality = selected_personality

        self.db.flush()

        return state

    def get_or_create(self, user_id: str) -> PersonalityState:
        """Get or create personality state with defaults."""
        state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        if not state:
            state = PersonalityState(user_id=user_id)
            self.db.add(state)
            self.db.flush()

        return state
