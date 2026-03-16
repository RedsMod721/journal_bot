"""Circuit breaker state table (Section 11.1.3)."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CircuitBreakerState(Base):
    __tablename__ = "circuit_breaker_state"

    scope_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="CLOSED")

    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    half_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('CLOSED', 'OPEN', 'HALF_OPEN')",
            name="ck_breaker_state",
        ),
        Index("idx_circuit_breaker_state_state", "state"),
        Index("idx_circuit_breaker_state_next_attempt", "next_attempt_at"),
    )
