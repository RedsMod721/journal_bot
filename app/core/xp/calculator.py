"""
Main XP Calculator that orchestrates XP distribution.

This is the primary entry point for processing journal entries and
distributing XP across themes and skills. It combines:
- Distribution strategies (equal, weighted, proportional)
- Title-based multipliers
- Event emission for downstream systems
- XP breakdown tracking in metadata
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.core.config_loader import ConfigLoader
from app.core.events import EventBus
from app.core.xp.base import XPDistributionStrategy
from app.core.xp.multipliers import calculate_title_multipliers
from app.models.skill import Skill
from app.models.theme import Theme

if TYPE_CHECKING:
    from app.models.journal_entry import JournalEntry


class XPCalculator:
    """
    Orchestrates XP distribution from journal entries.

    Combines a distribution strategy with title multipliers to award
    XP to themes and skills, emitting events for each award.

    Example:
        from app.core.xp import EqualDistributor, XPCalculator
        from app.core.events import get_event_bus
        from app.core.config_loader import get_config

        calculator = XPCalculator(
            strategy=EqualDistributor(),
            event_bus=get_event_bus(),
            config=get_config(),
        )

        summary = calculator.process_journal_entry(db, entry, categories)
        # summary = {
        #     "total_xp": 60.0,
        #     "awards": [
        #         {"type": "theme", "id": "...", "name": "Education", "xp": 20.0},
        #         {"type": "skill", "id": "...", "name": "Python", "xp": 40.0},
        #     ]
        # }
    """

    def __init__(
        self,
        strategy: XPDistributionStrategy,
        event_bus: EventBus,
        config: ConfigLoader,
    ) -> None:
        """
        Initialize the XP calculator.

        Args:
            strategy: Distribution strategy to use (equal, weighted, etc.)
            event_bus: Event bus for emitting xp.awarded events
            config: Config loader for base XP values
        """
        self.strategy = strategy
        self.event_bus = event_bus
        self.config = config

    def process_journal_entry(
        self,
        db: Session,
        entry: "JournalEntry",
        categories: dict,
    ) -> dict[str, Any]:
        """
        Process a journal entry and distribute XP.

        Args:
            db: Database session
            entry: The journal entry being processed
            categories: Detected categories from AI processing
                       {"themes": [{"id": str, "name": str}, ...],
                        "skills": [{"id": str, "name": str}, ...]}

        Returns:
            Summary dict with total XP and individual awards
        """
        # Get base XP from config
        base_xp = float(self.config.get("xp.base_journal_xp", 50))

        # Distribute XP using strategy
        distribution = self.strategy.distribute(entry, categories, base_xp)

        awards: list[dict[str, Any]] = []
        total_xp = 0.0

        # Preload target entities to avoid per-target queries
        theme_ids = [
            target_key.split(":", 1)[1]
            for target_key in distribution
            if target_key.startswith("theme:")
        ]
        skill_ids = [
            target_key.split(":", 1)[1]
            for target_key in distribution
            if target_key.startswith("skill:")
        ]

        themes = (
            db.query(Theme).filter(Theme.id.in_(theme_ids)).all()
            if theme_ids
            else []
        )
        skills = (
            db.query(Skill).filter(Skill.id.in_(skill_ids)).all()
            if skill_ids
            else []
        )

        theme_map = {theme.id: theme for theme in themes}
        skill_map = {skill.id: skill for skill in skills}

        # Process each target
        for target_key, strategy_xp in distribution.items():
            target_type, target_id = target_key.split(":", 1)

            # Calculate final XP with multipliers
            if target_type == "theme":
                entity = theme_map.get(target_id)
                if entity is None:
                    continue
                previous_level = entity.level
                final_xp = self._calculate_final_xp(
                    db, strategy_xp, entry.user_id, target_type, entity.name
                )
                entity.add_xp(final_xp)

                # Award XP to the entity
                self._update_xp_breakdown(entity, "journal", final_xp)
                awards.append({
                    "type": "theme",
                    "id": target_id,
                    "name": entity.name,
                    "xp": final_xp,
                })
                total_xp += final_xp

                # Emit event
                self.event_bus.emit("xp.awarded", {
                    "user_id": entry.user_id,
                    "amount": final_xp,
                    "source": "journal",
                    "target_type": "theme",
                    "target_id": target_id,
                })

                if entity.level > previous_level:
                    self.event_bus.emit("theme.leveled_up", {
                        "user_id": entry.user_id,
                        "theme_id": target_id,
                        "new_level": entity.level,
                        "theme_name": entity.name,
                    })

            elif target_type == "skill":
                entity = skill_map.get(target_id)
                if entity is None:
                    continue
                previous_level = entity.level
                final_xp = self._calculate_final_xp(
                    db, strategy_xp, entry.user_id, target_type, entity.name
                )
                entity.add_xp(final_xp)

                self._update_xp_breakdown(entity, "journal", final_xp)
                awards.append({
                    "type": "skill",
                    "id": target_id,
                    "name": entity.name,
                    "xp": final_xp,
                })
                total_xp += final_xp

                # Emit event
                self.event_bus.emit("xp.awarded", {
                    "user_id": entry.user_id,
                    "amount": final_xp,
                    "source": "journal",
                    "target_type": "skill",
                    "target_id": target_id,
                })

                if entity.level > previous_level:
                    self.event_bus.emit("skill.leveled_up", {
                        "user_id": entry.user_id,
                        "skill_id": target_id,
                        "new_level": entity.level,
                        "skill_name": entity.name,
                        "new_rank": entity.rank,
                    })

        db.commit()

        return {
            "total_xp": total_xp,
            "awards": awards,
        }

    def _calculate_final_xp(
        self,
        db: Session,
        base_xp: float,
        user_id: str,
        target_type: str,
        target_name: str | None = None,
        target_id: str | None = None,
    ) -> float:
        """
        Calculate final XP after applying title multipliers.

        Args:
            db: Database session
            base_xp: Base XP from distribution strategy
            user_id: User ID for multiplier lookup
            target_type: "theme" or "skill"
            target_name: Name of the target entity (preferred)
            target_id: ID of the target entity (fallback; triggers lookup)

        Returns:
            Final XP amount after multipliers
        """
        if not target_name and target_id:
            if target_type == "theme":
                entity = db.query(Theme).filter(Theme.id == target_id).first()
            else:
                entity = db.query(Skill).filter(Skill.id == target_id).first()
            target_name = entity.name if entity else None

        if not target_name:
            return base_xp

        multiplier = calculate_title_multipliers(db, user_id, target_type, target_name)
        return base_xp * multiplier

    def _update_xp_breakdown(
        self,
        entity: Theme | Skill,
        source: str,
        xp_amount: float,
    ) -> None:
        """
        Update the XP breakdown in entity metadata.

        Tracks XP sources for analytics and display:
        entity.metadata["xp_breakdown"] = {
            "journal": 500.0,
            "quest": 200.0,
            "practice": 100.0
        }

        Args:
            entity: Theme or Skill to update
            source: XP source ("journal", "quest", "practice")
            xp_amount: Amount of XP to add to breakdown
        """
        # Get the appropriate metadata field
        if isinstance(entity, Theme):
            metadata = entity.theme_metadata
        else:
            metadata = entity.skill_metadata

        # Build a new metadata dict to ensure SQLAlchemy detects changes
        current_breakdown = metadata.get("xp_breakdown", {})
        current_value = current_breakdown.get(source, 0.0)
        updated_breakdown = {**current_breakdown, source: current_value + xp_amount}
        updated_metadata = {**metadata, "xp_breakdown": updated_breakdown}

        if isinstance(entity, Theme):
            entity.theme_metadata = updated_metadata
        else:
            entity.skill_metadata = updated_metadata

    def _award_to_theme(
        self,
        db: Session,
        theme_id: str,
        xp_amount: float,
    ) -> Theme | None:
        """
        Award XP to a theme.

        Args:
            db: Database session
            theme_id: ID of the theme
            xp_amount: Amount of XP to award

        Returns:
            The Theme entity if found, None otherwise
        """
        theme = db.query(Theme).filter(Theme.id == theme_id).first()
        if theme:
            theme.add_xp(xp_amount)
        return theme

    def _award_to_skill(
        self,
        db: Session,
        skill_id: str,
        xp_amount: float,
    ) -> Skill | None:
        """
        Award XP to a skill.

        Args:
            db: Database session
            skill_id: ID of the skill
            xp_amount: Amount of XP to award

        Returns:
            The Skill entity if found, None otherwise
        """
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if skill:
            skill.add_xp(xp_amount)
        return skill
