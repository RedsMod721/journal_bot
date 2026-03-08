"""MB70 KB seed schema extensions for full-corpus ingestion.

Revision ID: b10000000007
Revises: b10000000006
Create Date: 2026-03-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b10000000007"
down_revision: Union[str, Sequence[str], None] = "b10000000006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns(table_name)}
    return column_name in columns


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(
    name: str, table_name: str, columns: list[str], *, unique: bool = False
) -> None:
    inspector = inspect(op.get_bind())
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if name in existing:
        return
    op.create_index(name, table_name, columns, unique=unique)


def _create_global_skills_extensions() -> None:
    table = "global_skills"
    _add_column_if_missing(
        table, sa.Column("source_skill_id", sa.String(length=120), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("category", sa.String(length=50), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("subcategory", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("difficulty_baseline", sa.String(length=20), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("typical_time_investment_minutes", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("xp_per_session_baseline", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("related_themes_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("learning_curve_type", sa.String(length=20), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_citations_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_grade", sa.String(length=8), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_limitations", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "expert_review_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "contradiction_flag",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_type", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_notes", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("hierarchy_level", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("parent_skill_ids_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(table, sa.Column("updated_at", sa.DateTime(), nullable=True))

    _create_index_if_missing(
        "idx_global_skills_source_skill_id", table, ["source_skill_id"], unique=False
    )
    _create_index_if_missing(
        "uq_global_skills_source_skill_id", table, ["source_skill_id"], unique=True
    )
    _create_index_if_missing(
        "idx_global_skills_category", table, ["category"], unique=False
    )


def _create_global_quests_extensions() -> None:
    table = "global_quests"
    _add_column_if_missing(
        table,
        sa.Column("source_quest_template_id", sa.String(length=160), nullable=True),
    )
    _add_column_if_missing(
        table, sa.Column("completion_type", sa.String(length=20), nullable=True)
    )
    _add_column_if_missing(
        table,
        sa.Column("primary_skill_source_id", sa.String(length=120), nullable=True),
    )
    _add_column_if_missing(
        table, sa.Column("secondary_skill_source_ids_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("difficulty_rating", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("estimated_effort", sa.String(length=255), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("xp_reward_min", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("xp_reward_max", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("cadence_or_target", sa.String(length=255), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_citations_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_grade", sa.String(length=8), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_limitations", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "expert_review_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "contradiction_flag",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_type", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_notes", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "exploit_risk_flag",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table, sa.Column("notes_for_review", sa.Text(), nullable=True)
    )
    _add_column_if_missing(table, sa.Column("updated_at", sa.DateTime(), nullable=True))

    _create_index_if_missing(
        "idx_global_quests_source_template_id",
        table,
        ["source_quest_template_id"],
        unique=False,
    )
    _create_index_if_missing(
        "uq_global_quests_source_template_id",
        table,
        ["source_quest_template_id"],
        unique=True,
    )
    _create_index_if_missing(
        "idx_global_quests_completion_type", table, ["completion_type"], unique=False
    )


def _create_global_insights_extensions() -> None:
    table = "global_insights"
    _add_column_if_missing(
        table, sa.Column("source_insight_id", sa.String(length=160), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("category", sa.String(length=50), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("strength_initial", sa.Float(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("trigger_patterns_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("contraindications_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_citations_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_grade", sa.String(length=8), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("evidence_limitations", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "expert_review_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "contradiction_flag",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_type", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_notes", sa.Text(), nullable=True)
    )
    _add_column_if_missing(table, sa.Column("updated_at", sa.DateTime(), nullable=True))

    _create_index_if_missing(
        "idx_global_insights_source_id", table, ["source_insight_id"], unique=False
    )
    _create_index_if_missing(
        "uq_global_insights_source_id", table, ["source_insight_id"], unique=True
    )
    _create_index_if_missing(
        "idx_global_insights_category", table, ["category"], unique=False
    )


def _create_rag_extensions() -> None:
    table = "rag_documents"
    _add_column_if_missing(
        table, sa.Column("source_document_id", sa.String(length=160), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("publication_date", sa.String(length=32), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("doi_link", sa.String(length=255), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("categories_json", sa.Text(), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("embedding_model", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "expert_review_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table,
        sa.Column(
            "contradiction_flag",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_type", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        table, sa.Column("contradiction_notes", sa.Text(), nullable=True)
    )
    _add_column_if_missing(table, sa.Column("updated_at", sa.DateTime(), nullable=True))

    _create_index_if_missing(
        "idx_rag_documents_source_document_id",
        table,
        ["source_document_id"],
        unique=False,
    )
    _create_index_if_missing(
        "uq_rag_documents_source_document_id",
        table,
        ["source_document_id"],
        unique=True,
    )


def upgrade() -> None:
    _create_global_skills_extensions()
    _create_global_quests_extensions()
    _create_global_insights_extensions()
    _create_rag_extensions()


def downgrade() -> None:
    # Conservative downgrade strategy: drop extension indexes only.
    for table_name, index_name in (
        ("global_skills", "idx_global_skills_source_skill_id"),
        ("global_skills", "uq_global_skills_source_skill_id"),
        ("global_skills", "idx_global_skills_category"),
        ("global_quests", "idx_global_quests_source_template_id"),
        ("global_quests", "uq_global_quests_source_template_id"),
        ("global_quests", "idx_global_quests_completion_type"),
        ("global_insights", "idx_global_insights_source_id"),
        ("global_insights", "uq_global_insights_source_id"),
        ("global_insights", "idx_global_insights_category"),
        ("rag_documents", "idx_rag_documents_source_document_id"),
        ("rag_documents", "uq_rag_documents_source_document_id"),
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
