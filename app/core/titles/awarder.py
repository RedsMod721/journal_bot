"""
Title awarder for checking and granting titles to users.

This module provides the TitleAwarder class which:
- Evaluates unlock conditions for all available titles
- Awards titles when conditions are met
- Emits events for title unlocks

Usage:
    from app.core.events import get_event_bus
    from app.core.titles.awarder import TitleAwarder

    event_bus = get_event_bus()
    awarder = TitleAwarder(event_bus)

    # Check and award all unlockable titles for a user
    new_titles = awarder.check_user_unlocks(db, user_id)

    # Manually award a specific title
    title = awarder.award_title(db, user_id, template_id, "manual_grant")
"""

from typing import TYPE_CHECKING

from app.core.events import EventBus
from app.core.titles.conditions import CONDITION_EVALUATORS, CompoundCondition
from app.crud.title import award_title_to_user, get_all_title_templates, get_user_titles
from app.models.title import TitleTemplate, UserTitle
from app.schemas.title import UserTitleCreate
from app.utils.logging_config import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)


class TitleAwarder:
    """
    Service for checking and awarding titles to users.

    Evaluates title unlock conditions and grants titles when met.
    Emits "title.unlocked" events when titles are awarded.

    Attributes:
        event_bus: EventBus instance for emitting title events
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the TitleAwarder.

        Args:
            event_bus: EventBus instance for emitting events
        """
        self._event_bus = event_bus
        self._compound_evaluator = CompoundCondition()
        self._evaluators = self._register_evaluators()

    def check_user_unlocks(self, db: "Session", user_id: str) -> list[UserTitle]:
        """
        Check all titles and award any that the user has unlocked.

        Iterates through all title templates, evaluates their unlock
        conditions, and awards titles the user doesn't already own.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            List of newly awarded UserTitle instances
        """
        all_templates = get_all_title_templates(db)
        user_titles = get_user_titles(db, user_id)
        owned_template_ids = {ut.title_template_id for ut in user_titles}

        newly_unlocked: list[UserTitle] = []

        for template in all_templates:
            if template.id in owned_template_ids:
                continue

            if not template.unlock_condition:
                continue

            if self._evaluate_condition(db, user_id, template.unlock_condition):
                user_title = self.award_title(
                    db=db,
                    user_id=user_id,
                    template_id=template.id,
                    unlock_reason="condition_met",
                )
                newly_unlocked.append(user_title)

        return newly_unlocked

    def _evaluate_condition(
        self, db: "Session", user_id: str, condition: dict
    ) -> bool:
        """
        Evaluate a title unlock condition.

        Routes to the appropriate evaluator based on condition type.
        Handles both simple and compound conditions.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Condition dict from TitleTemplate.unlock_condition

        Returns:
            True if the condition is met, False otherwise
        """
        if not condition:
            return False

        condition_type = condition.get("type")
        if not condition_type:
            logger.warning(
                "Condition missing type field",
                condition=condition,
            )
            return False

        if condition_type in ("and", "or", "not"):
            return self._compound_evaluator.evaluate(db, user_id, condition)

        evaluator = self._evaluators.get(condition_type)
        if evaluator is None:
            logger.warning(
                "Unknown condition type",
                condition_type=condition_type,
            )
            return False

        try:
            return evaluator.evaluate(db, user_id, condition)
        except Exception as e:
            logger.error(
                "Condition evaluation failed",
                condition_type=condition_type,
                error=str(e),
                exc_info=True,
            )
            return False

    def _register_evaluators(self) -> dict:
        """
        Register all condition evaluators.

        Returns:
            Dict mapping condition type strings to evaluator instances
        """
        return dict(CONDITION_EVALUATORS)

    def award_title(
        self,
        db: "Session",
        user_id: str,
        template_id: str,
        unlock_reason: str,
    ) -> UserTitle:
        """
        Award a title to a user.

        Creates a UserTitle record and emits a "title.unlocked" event.
        First title for a user is automatically equipped.

        Args:
            db: Database session
            user_id: User's UUID
            template_id: TitleTemplate UUID to award
            unlock_reason: Reason for the unlock (e.g., "condition_met", "manual_grant")

        Returns:
            The created UserTitle instance
        """
        existing_titles = get_user_titles(db, user_id)
        is_first_title = len(existing_titles) == 0

        user_title_data = UserTitleCreate(
            user_id=user_id,
            title_template_id=template_id,
            is_equipped=is_first_title,
        )
        user_title = award_title_to_user(db, user_title_data)

        db.refresh(user_title)
        template = user_title.title_template

        self._event_bus.emit(
            "title.unlocked",
            {
                "user_id": user_id,
                "title_id": user_title.id,
                "title_name": template.name if template else "Unknown",
                "title_rank": template.rank if template else "D",
            },
        )

        logger.info(
            "Title awarded",
            user_id=user_id,
            title_id=user_title.id,
            title_name=template.name if template else "Unknown",
            unlock_reason=unlock_reason,
        )

        return user_title
