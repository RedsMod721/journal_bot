"""
Theme model for Status Window API.

Themes represent broad life categories (e.g., Physical Health, Education, Spirituality)
that contain Skills, Titles, and Missions/Quests. They implement the core XP/leveling
system with exponential scaling.

Features:
- XP accumulation with automatic level-up handling
- Exponential XP scaling (100 * 1.15^level)
- Self-referential hierarchy (parent/sub-themes)
- Corrosion system for neglected themes
"""
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.skill import Skill
    from app.models.user import User


class Theme(Base):
    """
    Theme model representing a major life category in the Status Window system.

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Foreign key to the owning user
        name: Theme name (e.g., "Physical Health", "Education")
        description: Optional theme description
        level: Current level (starts at 0)
        xp: Current XP towards next level
        xp_to_next_level: XP required for next level-up
        corrosion_level: Degradation status if neglected
        parent_theme_id: Optional parent theme for hierarchy
        metadata: JSON field for extensibility

    Relationships:
        user: The user who owns this theme
        parent_theme: Optional parent theme (self-referential)
        sub_themes: Child themes (backref from parent_theme)
        skills: Skills associated with this theme
    """

    __tablename__ = "themes"

    # Primary key - UUID stored as string for SQLite compatibility
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign key to user
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Theme identity
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # XP and leveling system
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    xp_to_next_level: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    # Corrosion system - tracks neglect
    # Values: "Fresh", "Old", "Patterned", "Unrecovered"
    corrosion_level: Mapped[str] = mapped_column(String(20), default="Fresh", nullable=False)

    # Self-referential hierarchy for sub-themes
    parent_theme_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("themes.id"),
        nullable=True,
        index=True,
    )

    # Extensibility field for future attributes
    theme_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user: Mapped["User"] = relationship(
        "User",
        back_populates="themes",
    )

    # Self-referential relationship for theme hierarchy
    parent_theme: Mapped[Optional["Theme"]] = relationship(
        "Theme",
        remote_side="Theme.id",
        back_populates="sub_themes",
        foreign_keys="Theme.parent_theme_id",
    )

    sub_themes: Mapped[list["Theme"]] = relationship(
        "Theme",
        back_populates="parent_theme",
    )

    # Skills under this theme
    skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="theme",
        cascade="all, delete-orphan",
    )

    # =========================================================================
    # XP AND LEVELING METHODS
    # =========================================================================

    def add_xp(self, amount: float) -> None:
        """
        Add XP to the theme and handle level-ups.

        Adds the specified XP amount and triggers level_up() as many times
        as needed if the threshold is reached or exceeded. Overflow XP
        carries over to the next level.

        Args:
            amount: The amount of XP to add (must be non-negative)

        Raises:
            ValueError: If amount is negative

        Example:
            theme.add_xp(150)  # May trigger one or more level-ups
        """
        if amount < 0:
            raise ValueError("XP amount cannot be negative")

        self.xp += amount

        # Handle multiple level-ups if XP exceeds threshold multiple times
        while self.xp >= self.xp_to_next_level:
            self.level_up()

    def level_up(self) -> None:
        """
        Process a level-up for the theme.

        Increments the level, subtracts the required XP (keeping overflow),
        and recalculates the XP needed for the next level using exponential
        scaling.

        This method is called automatically by add_xp() when the threshold
        is reached. It should not typically be called directly.
        """
        # Subtract required XP, keeping overflow
        self.xp -= self.xp_to_next_level

        # Increment level
        self.level += 1

        # Recalculate XP requirement for next level
        self.xp_to_next_level = self.calculate_next_level_xp()

    def calculate_next_level_xp(self) -> float:
        """
        Calculate XP required for the next level.

        Uses exponential scaling formula: 100 * (1.15 ^ level)
        This creates a gradually increasing challenge as levels get higher.

        Returns:
            float: XP required to reach the next level

        Example:
            Level 0: 100.0 XP needed
            Level 1: 115.0 XP needed
            Level 5: ~201.1 XP needed
            Level 10: ~404.6 XP needed
        """
        return 100.0 * (1.15 ** self.level)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Theme {self.name} (Lv {self.level})>"
