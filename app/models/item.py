"""
Item models for Status Window API.

This module contains:
- ItemTemplate: Global item bank (shared across users)
- UserItem: User-specific item instances

Items can be consumables (food, drinks, activities) or persistent
(gadgets, diplomas). They provide buffs/debuffs and integrate with
the karma system.

Usage:
    from app.models.item import ItemTemplate, UserItem

    # Create a template
    template = ItemTemplate(
        name="Coffee",
        item_type="consumable",
        rarity="common",
        effect={"focus_boost": 15, "hp_cost": -10},
        is_consumable=True,
        effect_duration_minutes=240
    )

    # Award to user
    user_item = UserItem(
        user_id=user.id,
        template_id=template.id,
        source="quest_reward",
        source_id=quest.id
    )
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ItemTemplate(Base):
    """
    Global item template bank (shared across users).

    Stores the base definition for all items. User-specific instances
    reference these templates via UserItem.

    Attributes:
        id: Unique identifier (UUID string)
        name: Display name (unique)
        description: Flavor text description
        item_type: Category (consumable, equipment, collectible, etc.)
        rarity: Rarity tier (common, uncommon, rare, epic, legendary)
        effect: JSON containing buff/debuff effects
        duration_days: How long the item lasts (for time-limited items)
        is_consumable: Whether the item is consumed on use
        effect_duration_minutes: How long effects last after consumption
        category: Grouping category (food, drink, activity, gadget, etc.)
        metadata: Additional flexible data

    Categories:
        - food_drink: Consumables like coffee, snacks
        - activity: Brainrot or productive activities
        - gadget: Purchased items with passive effects
        - diploma: Achievements with permanent buffs
        - drug: Caffeine, medication, etc.
    """

    __tablename__ = "item_templates"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Core attributes
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    # Classification
    item_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="consumable",
        index=True,
    )
    rarity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="common",
    )

    # Effects as JSON
    # Format: {"xp_multiplier": 1.1, "hp_cost": -10, "focus_boost": 15}
    effect: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    # Duration settings
    duration_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    is_consumable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    effect_duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Categorization
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    # Flexible metadata
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user_items: Mapped[list["UserItem"]] = relationship(
        "UserItem",
        back_populates="template",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<ItemTemplate {self.name} ({self.rarity})>"


class UserItem(Base):
    """
    User-specific item instance.

    Represents an item in a user's inventory. References an ItemTemplate
    and stores user-specific state like acquisition date, equipped status,
    and consumption tracking.

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Owner of this item
        template_id: Reference to ItemTemplate
        acquired_at: When the user obtained this item
        expires_at: When the item expires (if time-limited)
        is_equipped: Whether the item is actively equipped
        is_consumed: Whether the item has been used
        consumed_at: When the item was consumed
        source: How the user obtained the item (quest_reward, purchase, etc.)
        source_id: ID of the source (quest ID, shop transaction ID, etc.)
        metadata: User-specific flexible data

    Indexes:
        - user_id: Fast lookup by user
        - template_id: Fast lookup by item type
        - (user_id, is_equipped): Fast equipped item queries
    """

    __tablename__ = "user_items"

    # Define indexes
    __table_args__ = (
        Index("ix_user_items_user_equipped", "user_id", "is_equipped"),
    )

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("item_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Acquisition info
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    # State tracking
    is_equipped: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_consumed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Provenance tracking
    source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )

    # Flexible metadata
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_items",
    )

    template: Mapped["ItemTemplate"] = relationship(
        "ItemTemplate",
        back_populates="user_items",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = "equipped" if self.is_equipped else "consumed" if self.is_consumed else "inventory"
        return f"<UserItem {self.template_id[:8]}... ({status})>"
