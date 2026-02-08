"""
EventLog model for Status Window API.

EventLog stores all events emitted by the event system for auditing,
analytics, and debugging purposes. Each event is stored with its
type, payload, and timestamp.

Usage:
    from app.models.event_log import EventLog

    log = EventLog(
        user_id=user.id,
        event_type="xp.awarded",
        event_payload={"amount": 50, "source": "journal"}
    )
    db.add(log)
    db.commit()
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class EventLog(Base):
    """
    Event log model for tracking all system events.

    Stores every event emitted by the EventBus for:
    - Auditing and debugging
    - Analytics and reporting
    - Event replay/recovery

    Attributes:
        id: Unique identifier (UUID string)
        user_id: User who triggered the event
        event_type: Type of event (e.g., "xp.awarded", "title.unlocked")
        event_payload: JSON payload containing event data
        created_at: Timestamp when event occurred

    Indexes:
        - user_id: Fast lookup by user
        - event_type: Fast lookup by event type
        - created_at: Fast time-based queries
        - (user_id, event_type): Composite for filtered user queries
    """

    __tablename__ = "event_logs"

    # Define indexes
    __table_args__ = (
        Index("ix_event_logs_user_id", "user_id"),
        Index("ix_event_logs_event_type", "event_type"),
        Index("ix_event_logs_created_at", "created_at"),
        Index("ix_event_logs_user_event", "user_id", "event_type"),
    )

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign key to user
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Event identification
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Event data as JSON
    event_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user: Mapped["User"] = relationship(
        "User",
        back_populates="event_logs",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<EventLog {self.event_type} user={self.user_id[:8]}...>"
