"""
Personality likability learning.

Implements Section 3.4.3 (Likability) from architecture.
"""
import json
from typing import Literal

from sqlalchemy.orm import Session

from src.core.personality_selection import PERSONALITY_LIKABILITY_COLUMN
from src.db.models.personality import PersonalityMessage, PersonalityState

_DELTA_MAP = {
    "thumbs_up": 5,
    "thumbs_down": -10,
    "explicit_positive": 10,
    "explicit_negative": -15,
}


class LikabilityService:
    """Manage personality likability learning."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def set_likability_scores(
        self,
        user_id: str,
        likability_scores: dict[str, int],
    ) -> PersonalityState:
        """Persist absolute likability scores for all canonical personalities."""
        state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        if not state:
            state = PersonalityState(user_id=user_id)
            self.db.add(state)
            self.db.flush()

        for personality, column in PERSONALITY_LIKABILITY_COLUMN.items():
            setattr(state, column, likability_scores[personality])

        self.db.commit()
        self.db.refresh(state)
        return state

    def apply_feedback(
        self,
        user_id: str,
        message_id: str,
        feedback_type: Literal["thumbs_up", "thumbs_down", "explicit_positive", "explicit_negative"],
    ) -> dict:
        """
        Apply user feedback to likability.

        Rules:
        - thumbs_up: +5 (capped at 100)
        - thumbs_down: -10 (capped at 0)
        - explicit_positive: +10
        - explicit_negative: -15

        Returns updated likability values.
        """
        message = (
            self.db.query(PersonalityMessage)
            .filter(
                PersonalityMessage.id == message_id,
                PersonalityMessage.user_id == user_id,
            )
            .first()
        )
        if not message:
            raise ValueError("Message not found")

        personality = message.personality

        state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        if not state:
            raise ValueError("Personality state not found")

        try:
            context = json.loads(message.context_data or "{}")
            multi_personality = context.get("multi_personality")
            if isinstance(multi_personality, dict):
                impact_multiplier = float(
                    multi_personality.get("impact_multiplier", 1.0)
                )
            else:
                impact_multiplier = float(context.get("impact_multiplier", 1.0))
        except Exception:
            impact_multiplier = 1.0

        base_delta = _DELTA_MAP[feedback_type]
        delta = int(base_delta * impact_multiplier)

        column = PERSONALITY_LIKABILITY_COLUMN[personality]
        current = getattr(state, column)
        new_value = max(0, min(100, current + delta))
        setattr(state, column, new_value)

        self.db.flush()

        return {
            "personality": personality,
            "old_likability": current,
            "new_likability": new_value,
            "delta": delta,
            "impact_multiplier": impact_multiplier,
        }

    def get_likability_scores(self, user_id: str) -> dict:
        """Get all likability scores for user."""
        state = (
            self.db.query(PersonalityState)
            .filter(PersonalityState.user_id == user_id)
            .first()
        )
        if not state:
            return {
                "observer": 80,
                "therapist": 70,
                "coach": 60,
                "sassy": 50,
                "wargod": 40,
                "raphael": 60,
            }

        return {
            pid: getattr(state, col)
            for pid, col in PERSONALITY_LIKABILITY_COLUMN.items()
        }
