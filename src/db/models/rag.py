"""RAG document registry metadata table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_document_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True, unique=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="global")
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_citation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    doi_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    categories_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    qdrant_collection: Mapped[str] = mapped_column(String(100), nullable=False)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expert_review_priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    contradiction_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradiction_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contradiction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_rag_documents_source_document_id", "source_document_id"),
        Index("idx_rag_documents_scope", "scope"),
        Index("idx_rag_documents_content_hash", "content_hash"),
        Index(
            "idx_rag_documents_collection_point", "qdrant_collection", "qdrant_point_id"
        ),
        CheckConstraint("scope IN ('global','user')", name="ck_rag_documents_scope"),
        CheckConstraint("verified IN (0,1)", name="ck_rag_documents_verified"),
        CheckConstraint(
            "expert_review_priority IN (0,1)",
            name="ck_rag_documents_expert_review_priority",
        ),
        CheckConstraint(
            "contradiction_flag IN (0,1)", name="ck_rag_documents_contradiction_flag"
        ),
    )
