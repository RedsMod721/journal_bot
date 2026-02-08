"""
User stats model for Status Window API.

UserStats represents the status bars (HP, MP, Mental Health, etc.) that track
the user's current state. This is a one-to-one relationship with User.

Status bars are updated by:
- Journal entries (AI sentiment analysis)
- Mission/Quest completion
- Item usage

Features:
- All stats use 0-100 scale for consistency
- HP/MP represent immediate physical/mental energy
- Other stats represent longer-term states (health, relationships, etc.)
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.utils.database import Base


class UserStats(Base):
    """
    UserStats model representing a user's status bars in the Status Window system.

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Foreign key to the owning user (one-to-one, unique)
        hp: Hit Points - Physical energy (0-100)
        mp: Mana Points - Mental energy/focus capacity (0-100)
        mental_health: Mood/anxiety/depression level (0-100)
        physical_health: Fitness/nutrition/sleep quality (0-100)
        relationship_quality: Social connection quality (0-100)
        socialization_level: Recent social activity level (0-100)
        updated_at: Last time stats were modified

    Relationships:
        user: The user who owns these stats (one-to-one)
    """

    __tablename__ = "user_stats"

    # Type annotations for all attributes (helps Pylance understand types)
    id: str
    user_id: str
    hp: int
    mp: int
    mental_health: int
    physical_health: int
    relationship_quality: int
    socialization_level: int
    updated_at: datetime

    # Primary key - UUID stored as string for SQLite compatibility
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign key to user - unique constraint for one-to-one relationship
    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    # =========================================================================
    # STATUS BARS
    # All use 0-100 scale for consistency
    # =========================================================================

    # HP (Hit Points) - Physical energy/health
    hp = Column(Integer, default=100, nullable=False)

    # MP (Mana Points) - Mental energy/focus capacity
    mp = Column(Integer, default=100, nullable=False)

    # Mental Health - Mood/anxiety/depression level
    mental_health = Column(Integer, default=70, nullable=False)

    # Physical Health - Fitness/nutrition/sleep quality
    physical_health = Column(Integer, default=70, nullable=False)

    # Relationship - Social connection quality
    relationship_quality = Column(Integer, default=50, nullable=False)

    # Socialization - Recent social activity level
    socialization_level = Column(Integer, default=50, nullable=False)

    # Timestamp for tracking updates
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user = relationship(
        "User",
        back_populates="stats",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<UserStats HP:{self.hp} MP:{self.mp}>"
