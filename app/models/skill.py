"""
Skill model for Status Window API.

Skills represent specific competencies that level up through practice (e.g., Python Programming,
Cooking, Spanish Language). They support skill trees via parent-child relationships and
implement practice tracking with XP rewards.

Features:
- XP accumulation with automatic level-up handling
- Exponential XP scaling (50 * 1.2^level)
- Rank progression (Beginner -> Amateur -> Intermediate -> Advanced -> Expert -> Master)
- Practice time tracking with XP multipliers
- Self-referential hierarchy (parent/child skills for skill trees)
- Optional association with themes
"""
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.theme import Theme
    from app.models.user import User


class Skill(Base):
    """
    Skill model representing a specific competency in the Status Window system.

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Foreign key to the owning user
        theme_id: Optional foreign key to parent theme
        parent_skill_id: Optional parent skill for skill trees
        name: Skill name (e.g., "Python Programming", "Cooking")
        description: Optional skill description
        level: Current level (starts at 0)
        xp: Current XP towards next level
        xp_to_next_level: XP required for next level-up
        rank: Current rank based on level
        practice_time_minutes: Total practice time accumulated
        difficulty: Skill difficulty rating
        skill_metadata: JSON field for extensibility

    Relationships:
        user: The user who owns this skill
        theme: Optional theme this skill belongs to
        parent_skill: Optional parent skill (self-referential)
        child_skills: Child skills (backref from parent_skill)

    Rank Thresholds:
        - Level 0-4: Beginner
        - Level 5-14: Amateur
        - Level 15-29: Intermediate
        - Level 30-49: Advanced
        - Level 50-79: Expert
        - Level 80+: Master
    """

    __tablename__ = "skills"

    # Primary key - UUID stored as string for SQLite compatibility
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign key to user (required)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Foreign key to theme (optional - skill can exist without theme)
    theme_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("themes.id"),
        nullable=True,
        index=True,
    )

    # Self-referential hierarchy for skill trees
    parent_skill_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("skills.id"),
        nullable=True,
        index=True,
    )

    # Skill identity
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # XP and leveling system
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    xp_to_next_level: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    # Rank system (Beginner -> Amateur -> Intermediate -> Advanced -> Expert -> Master)
    rank: Mapped[str] = mapped_column(String(20), default="Beginner", nullable=False)

    # Practice tracking
    practice_time_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Difficulty rating
    difficulty: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)

    # Extensibility field for future attributes
    skill_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user: Mapped["User"] = relationship(
        "User",
        back_populates="skills",
    )

    theme: Mapped[Optional["Theme"]] = relationship(
        "Theme",
        back_populates="skills",
    )

    # Self-referential relationship for skill trees
    parent_skill: Mapped[Optional["Skill"]] = relationship(
        "Skill",
        remote_side="Skill.id",
        back_populates="child_skills",
        foreign_keys="Skill.parent_skill_id",
    )

    child_skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="parent_skill",
    )

    # =========================================================================
    # PRACTICE TIME METHODS
    # =========================================================================

    def add_practice_time(self, minutes: int, xp_multiplier: float = 1.0) -> None:
        """
        Log practice time and award XP.

        Increments the total practice time and awards XP based on the
        formula: minutes * 0.5 * xp_multiplier.

        Args:
            minutes: Number of minutes practiced (must be non-negative)
            xp_multiplier: Optional multiplier for XP (default 1.0)

        Raises:
            ValueError: If minutes is negative

        Example:
            skill.add_practice_time(30)  # 30 min * 0.5 = 15 XP
            skill.add_practice_time(30, xp_multiplier=2.0)  # 30 XP
        """
        if minutes < 0:
            raise ValueError("Practice time cannot be negative")

        # Increment total practice time
        self.practice_time_minutes += minutes

        # Calculate and award XP (0.5 XP per minute base rate)
        xp_gained = minutes * 0.5 * xp_multiplier
        self.add_xp(xp_gained)

    # =========================================================================
    # XP AND LEVELING METHODS
    # =========================================================================

    def add_xp(self, amount: float) -> None:
        """
        Add XP to the skill and handle level-ups.

        Adds the specified XP amount and triggers level_up() as many times
        as needed if the threshold is reached or exceeded. Overflow XP
        carries over to the next level.

        Args:
            amount: The amount of XP to add (must be non-negative)

        Raises:
            ValueError: If amount is negative

        Example:
            skill.add_xp(100)  # May trigger one or more level-ups
        """
        if amount < 0:
            raise ValueError("XP amount cannot be negative")

        self.xp += amount

        # Handle multiple level-ups if XP exceeds threshold multiple times
        while self.xp >= self.xp_to_next_level:
            self.level_up()

    def level_up(self) -> None:
        """
        Process a level-up for the skill.

        Increments the level, subtracts the required XP (keeping overflow),
        recalculates the XP needed for the next level using exponential
        scaling, and updates the rank.

        This method is called automatically by add_xp() when the threshold
        is reached. It should not typically be called directly.
        """
        # Subtract required XP, keeping overflow
        self.xp -= self.xp_to_next_level

        # Increment level
        self.level += 1

        # Recalculate XP requirement for next level (50 * 1.2^level)
        self.xp_to_next_level = self.calculate_next_level_xp()

        # Update rank based on new level
        self.update_rank()

    def calculate_next_level_xp(self) -> float:
        """
        Calculate XP required for the next level.

        Uses exponential scaling formula: 50 * (1.2 ^ level)
        This creates a gradually increasing challenge as levels get higher.

        Returns:
            float: XP required to reach the next level

        Example:
            Level 0: 50.0 XP needed
            Level 1: 60.0 XP needed
            Level 5: ~124.4 XP needed
            Level 10: ~309.6 XP needed
        """
        return 50.0 * (1.2 ** self.level)

    def update_rank(self) -> None:
        """
        Update rank based on current level.

        Rank thresholds:
            - Level 0-4: Beginner
            - Level 5-14: Amateur
            - Level 15-29: Intermediate
            - Level 30-49: Advanced
            - Level 50-79: Expert
            - Level 80+: Master

        This method is called automatically by level_up() but can also
        be called directly to ensure rank consistency.
        """
        if self.level < 5:
            self.rank = "Beginner"
        elif self.level < 15:
            self.rank = "Amateur"
        elif self.level < 30:
            self.rank = "Intermediate"
        elif self.level < 50:
            self.rank = "Advanced"
        elif self.level < 80:
            self.rank = "Expert"
        else:
            self.rank = "Master"

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Skill {self.name} (Lv {self.level}, {self.rank})>"
